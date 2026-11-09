"""Authenticated loopback backend; one model and one serial inference queue."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import argparse
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import queue
import threading
import time
import traceback
import uuid
import warnings
from common import APP, VERSION, atomic_json, read_json, validate, wav_info, inference_kwargs, sampling_switch_supported


class Engine:
    def __init__(self, home, token):
        self.home = Path(home).resolve()
        self.config = read_json(self.home / 'config.json')
        self.token = token
        self.instance = uuid.uuid4().hex
        self.phase = 'loading'
        self.error = None
        self.runtime = {}
        self.active = None
        self.gate = threading.RLock()
        self.queue = queue.Queue(maxsize=self.config.get('max_queue',4))
        self.stopping = False
        self.jobs_dir = self.home / '.state/jobs'
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        (self.home / 'outputs').mkdir(exist_ok=True)
        # Interrupted tasks from a previous process are never reported as still running.
        for file in self.jobs_dir.glob('*.json'):
            try:
                job = read_json(file)
            except (OSError,ValueError):
                continue
            if job.get('status') in ('queued','running'):
                job.update(status='failed', error='Backend exited before finishing this task', finished_at=time.time())
                atomic_json(file, job)

    def status(self):
        with self.gate:
            return {'app':APP,'version':VERSION,'phase':self.phase,'error':self.error,
                    'pid':os.getpid(),'instance':self.instance,'active_job':self.active,
                    'queued':self.queue.qsize(),'use_qwen_emo':self.config.get('use_qwen_emo',False),
                    'runtime':self.runtime,
                    'output_dir':str(self.home / 'outputs')}

    def submit(self, args):
        params = validate(args,self.config)
        with self.gate:
            if self.phase != 'ready' or self.stopping:
                raise ValueError(f'Backend is {self.phase}; poll indextts_status first')
            if not params['do_sample'] and not self.runtime.get('sampling_switch_supported',False):
                raise ValueError('Installed IndexTTS hardcodes do_sample=True. This bundle cannot disable sampling; upstream supports it. Keep do_sample=true.')
            for parameter,limit in [('max_mel_tokens','max_mel_tokens'),('max_tokens_per_segment','max_text_tokens')]:
                if params[parameter]>self.runtime.get(limit,4096):
                    raise ValueError(f'{parameter} exceeds loaded model limit {self.runtime[limit]}')
            ident=uuid.uuid4().hex
            job={'job_id':ident,'status':'queued','created_at':time.time(),'parameters':params}
            if self.queue.full():
                raise ValueError('Queue is full; wait for existing jobs')
            atomic_json(self.jobs_dir / (ident+'.json'),job)
            self.queue.put_nowait(ident)
            return job

    def run(self):
        try:
            tts_root=Path(self.config['tts_root']).resolve()
            os.chdir(tts_root)
            sys.path.insert(0,str(tts_root))
            sys.path.insert(0,str(tts_root/'indextts'))
            # Use only installed models; unexpected network downloads fail explicitly.
            os.environ['HF_HUB_OFFLINE']='1'
            os.environ['TRANSFORMERS_OFFLINE']='1'
            cache=self.home/'.state/cache'
            cache.mkdir(parents=True,exist_ok=True)
            os.environ['NUMBA_CACHE_DIR']=str(cache/'numba')
            os.environ['MPLCONFIGDIR']=str(cache/'matplotlib')
            os.environ['TORCH_HOME']=str(cache/'torch')
            import torch
            from indextts.infer_v2_5 import IndexTTS2
            model=IndexTTS2(cfg_path=str(tts_root/'checkpoints/config.yaml'),model_dir=str(tts_root/'checkpoints'),
                            use_bf16=bool(self.config.get('half_precision',True) and torch.cuda.is_available() and torch.cuda.is_bf16_supported()),
                            use_cuda_kernel=False,use_qwen_emo=self.config.get('use_qwen_emo',False))
            with self.gate:
                self.runtime={'device':str(model.device),'precision':'bf16' if model.use_bf16 else 'fp32',
                              'low_vram':model.low_vram,'max_mel_tokens':int(model.cfg.gpt.max_mel_tokens),
                              'max_text_tokens':int(model.cfg.gpt.max_text_tokens),
                              'sampling_switch_supported':sampling_switch_supported(tts_root/'indextts/infer_v2_5.py'),
                              'reference_max_seconds':15}
                self.phase='ready'
            model.gr_progress=self.report_progress
            while True:
                ident=self.queue.get()
                file=self.jobs_dir/(ident+'.json')
                with self.gate:
                    self.active=ident
                    job=read_json(file)
                    job.update(status='running',started_at=time.time(),stage='starting inference',progress=0.)
                    atomic_json(file,job)
                try:
                    p=job['parameters']
                    if 'seed' in p:
                        import random
                        import numpy as np
                        random.seed(p['seed']); np.random.seed(p['seed']); torch.manual_seed(p['seed'])
                        if torch.cuda.is_available():
                            torch.cuda.manual_seed_all(p['seed'])
                    output=self.home/'outputs'/(ident+'.wav')
                    with warnings.catch_warnings(record=True) as caught:
                        warnings.simplefilter('always',RuntimeWarning)
                        model.infer(**inference_kwargs(p,output,model))
                    audio=wav_info(output)
                    elapsed=time.time()-job['started_at']
                    job.update(status='succeeded',audio=audio,progress=1.,stage='completed',
                               elapsed_seconds=round(elapsed,3),rtf=round(elapsed/audio['duration_seconds'],3))
                    job['warnings']=[str(w.message) for w in caught]
                    job['possibly_truncated']=any('max_mel_tokens' in str(w.message) for w in caught)
                except Exception as exc:
                    traceback.print_exc()
                    job.update(status='failed',error=f'{type(exc).__name__}: {exc}')
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                finally:
                    with self.gate:
                        if job['status']=='failed':
                            job['stage']='failed'
                        job['finished_at']=time.time()
                        atomic_json(file,job)
                        self.active=None
                        self.queue.task_done()
        except Exception as exc:
            traceback.print_exc()
            with self.gate:
                self.phase='failed'
                self.error=f'{type(exc).__name__}: {exc}'

    def report_progress(self,value,desc=''):
        # The upstream callback reports model phases, not a reliable whole-job ETA.
        with self.gate:
            if not self.active:
                return
            file=self.jobs_dir/(self.active+'.json')
            job=read_json(file)
            job.update(progress=float(value),stage=str(desc),updated_at=time.time())
            atomic_json(file,job)


def serve(home):
    home=Path(home).resolve()
    token=(home/'.state/token').read_text(encoding='ascii').strip()
    engine=Engine(home,token)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):
            pass

        def reply(self,status,value):
            data=json.dumps(value,ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type','application/json; charset=utf-8')
            self.send_header('Content-Length',str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def handle_request(self):
            if not hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+token):
                self.reply(401,{'error':'Unauthorized'}); return
            try:
                if self.command=='GET' and self.path=='/status':
                    self.reply(200,engine.status())
                elif self.command=='GET' and self.path.startswith('/jobs/'):
                    ident=self.path[len('/jobs/'):]
                    if len(ident)!=32 or any(c not in '0123456789abcdef' for c in ident):
                        raise ValueError('Invalid job_id')
                    self.reply(200,read_json(engine.jobs_dir/(ident+'.json')))
                elif self.command=='POST' and self.path=='/jobs':
                    length=int(self.headers.get('Content-Length','0'))
                    if not 0 < length <= 100000:
                        raise ValueError('Invalid request size')
                    args=json.loads(self.rfile.read(length))
                    self.reply(200,engine.submit(args))
                elif self.command=='POST' and self.path=='/stop':
                    with engine.gate:
                        if engine.active or engine.queue.unfinished_tasks or engine.phase=='loading':
                            raise ValueError('Backend busy/loading; wait before stopping')
                        engine.stopping=True
                        engine.phase='stopping'
                    self.reply(200,{'stopped':True,'pid':os.getpid()})
                    threading.Thread(target=self.server.shutdown,daemon=True).start()
                else:
                    self.reply(404,{'error':'Unknown endpoint'})
            except Exception as exc:
                self.reply(400,{'error':str(exc)})

        do_GET=handle_request
        do_POST=handle_request
    server=ThreadingHTTPServer(('127.0.0.1',engine.config['port']),Handler)
    threading.Thread(target=engine.run,daemon=True).start()
    server.serve_forever(poll_interval=.2)
    server.server_close()


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--home',required=True)
    serve(parser.parse_args().home)
