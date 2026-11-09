"""IndexTTS MCP stdio bridge, standard library only, Python >=3.10."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import argparse
import json
import os
import secrets
import shutil
import socket
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from common import APP, VERSION, EMOTIONS, LANGUAGES, atomic_json, read_json, validate, wav_info, number, audio_path

HOME=Path(os.environ.get('INDEXTTS_MCP_HOME',Path(__file__).resolve().parent)).resolve()


class Bridge:
    def __init__(self,home=HOME):
        self.home=Path(home).resolve()
        self.config=read_json(self.home/'config.json')
        self.root=Path(self.config['tts_root']).resolve()
        self.port=number(self.config['port'],'port',1024,65535,True)
        self.state=self.home/'.state'
        self.http=urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def request(self,path,data=None):
        token=(self.state/'token').read_text(encoding='ascii').strip()
        req=urllib.request.Request(f'http://127.0.0.1:{self.port}'+path,
                                   data=json.dumps(data).encode() if data is not None else None,
                                   headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
        try:
            with self.http.open(req,timeout=4) as response:
                value=json.loads(response.read(2*1024*1024))
        except urllib.error.HTTPError as exc:
            try:
                message=json.loads(exc.read(4096)).get('error',str(exc))
            except ValueError:
                message=str(exc)
            raise ValueError(message) from exc
        if path=='/status' and value.get('app')!=APP:
            raise ValueError('Port belongs to another application')
        return value

    def status(self):
        try:
            result=self.request('/status')
            return {'online':True,'version_matches':result.get('version')==VERSION,**result}
        except (OSError,ValueError) as exc:
            return {'online':False,'error':str(exc),'log':str(self.state/'backend.log'),
                    'launch':read_json(self.state/'launch.json') if (self.state/'launch.json').exists() else None,
                    'next_step':'Call indextts_start, then poll indextts_status; inspect log if loading fails'}

    def environment(self):
        required=['config.yaml','gpt.pth','s2mel.pth','codec.pth','multilingual_zh_ja_yue_char_del.tiktoken','wav2vec2bert_stats.pt']
        return {'tts_root':str(self.root),'python':str(self.root/'python_embeded/python.exe'),
                'python_exists':(self.root/'python_embeded/python.exe').is_file(),
                'missing_models':[f for f in required if not (self.root/'checkpoints'/f).is_file()],
                'languages':LANGUAGES,'emotion_vector_order':EMOTIONS,'config':self.config,
                'outputs':str(self.home/'outputs'),'status':self.status()}

    def references(self):
        directory=self.root/'examples'
        named=[]
        for name,entry in self.voice_registry().items():
            path=self.voice_path(entry)
            named.append({'name':name,'path':str(path),'exists':path.is_file(),
                          'description':entry.get('description',''),'kind':'speaker',
                          'source_type':entry.get('source_type','plugin')})
        return {'voices':named,'references':[{'path':str(p.resolve()),'bytes':p.stat().st_size,
                               'kind':'emotion' if p.stem.startswith('emo_') else 'speaker'}
                              for p in sorted(directory.glob('*.wav'))],
                'note':'Use voice=<name> or reference_audio=<absolute path>. WebUI presets contribute speaker audio only; emotion/sampling settings are not silently applied. Plugin names take priority.',
                'reference_max_seconds':15,'warnings':getattr(self,'preset_warnings',[])}

    def voice_registry(self):
        file=self.home/'voices.json'
        registry=read_json(file) if file.is_file() else {}
        self.preset_warnings=[]
        # Upstream presets are read-only discoveries; explicit plugin voices win.
        for preset in sorted((self.root/'outputs/presets').glob('*/preset.json')):
            try:
                data=read_json(preset)
                relative=data.get('prompt_audio')
                if not isinstance(relative,str) or not relative:
                    continue
                audio=(preset.parent/relative).resolve()
                if not audio.is_relative_to(preset.parent.resolve()):
                    raise ValueError('prompt_audio must stay within its preset directory')
                registry.setdefault(preset.parent.name,{'path':str(audio),'description':'IndexTTS WebUI preset (speaker audio only)',
                                                        'source_type':'webui_preset'})
            except (OSError,ValueError,TypeError,AttributeError) as exc:
                self.preset_warnings.append(f'{preset.parent.name}: {exc}')
        return registry

    def voice_path(self,entry):
        path=Path(entry['path'])
        return (path if path.is_absolute() else self.home/path).resolve()

    def register_voice(self,name,reference_audio,description=''):
        if not isinstance(name,str) or not name.strip() or len(name)>80:
            raise ValueError('name must be nonempty and at most 80 characters')
        name=name.strip()
        if not isinstance(description,str) or len(description)>500:
            raise ValueError('description must be a string of at most 500 characters')
        source=Path(audio_path(reference_audio))
        self.state.mkdir(parents=True,exist_ok=True)
        lock=self.state/'voices.lock'
        try:
            handle=lock.open('x')
        except FileExistsError as exc:
            raise ValueError('Voice registry is busy; retry after the current registration') from exc
        destination=None
        try:
            handle.close()
            registry=read_json(self.home/'voices.json') if (self.home/'voices.json').exists() else {}
            if name in registry:
                raise ValueError(f'Voice {name!r} already exists; choose a different name')
            directory=self.home/'voices'; directory.mkdir(exist_ok=True)
            destination=directory/(uuid.uuid4().hex+source.suffix.lower())
            shutil.copyfile(source,destination)
            registry[name]={'path':destination.relative_to(self.home).as_posix(),'description':description,'source_type':'plugin'}
            atomic_json(self.home/'voices.json',registry)
            return {'name':name,'path':str(destination),'registered':True,
                    'note':'Available immediately by voice name. Rebuild the ZIP to include this reference in a distributable package.'}
        except Exception:
            if destination is not None:
                destination.unlink(missing_ok=True)
            raise
        finally:
            lock.unlink(missing_ok=True)

    def start(self):
        status=self.status()
        if status['online']:
            return {'started':False,**status}
        self.state.mkdir(parents=True,exist_ok=True)
        lock=self.state/'start.lock'
        try:
            with lock.open('x',encoding='ascii') as marker:
                marker.write(str(os.getpid()))
        except FileExistsError:
            if time.time()-lock.stat().st_mtime < 30:
                return {'started':False,'reason':'Another client is launching the backend; poll status'}
            raise ValueError(f'Stale start lock: inspect {lock} before removing it')
        try:
            previous=self.state/'launch.json'
            if previous.exists() and time.time()-read_json(previous).get('time',0)<120:
                return {'started':False,'reason':'Recent launch; poll status and inspect backend.log'}
            info=self.environment()
            if not info['python_exists'] or info['missing_models']:
                raise ValueError(f'Installation incomplete: {info}')
            # Test the port before replacing the token used by an existing process.
            with socket.socket() as probe:
                try:
                    probe.bind(('127.0.0.1',self.port))
                except OSError as exc:
                    raise ValueError('Port is occupied; refusing to launch another backend') from exc
            token=self.state/'token'
            if not token.exists():
                with token.open('x',encoding='ascii') as file:
                    file.write(secrets.token_hex(32))
            python=self.root/'python_embeded/python.exe'
            flags=subprocess.CREATE_NO_WINDOW|subprocess.CREATE_NEW_PROCESS_GROUP if os.name=='nt' else 0
            env=os.environ.copy(); env['PYTHONUTF8']='1'; env['PYTHONDONTWRITEBYTECODE']='1'
            with (self.state/'backend.log').open('ab') as log:
                child=subprocess.Popen([str(python),'-u',str(Path(__file__).resolve().parent/'backend.py'),'--home',str(self.home)],
                                       cwd=self.root,stdin=subprocess.DEVNULL,stdout=log,stderr=log,env=env,creationflags=flags)
            launch={'pid':child.pid,'time':time.time(),'log':str(self.state/'backend.log')}
            atomic_json(previous,launch)
            return {'started':True,**launch,'next_step':'Model loads asynchronously. Poll indextts_status until phase=ready; do not start repeatedly.'}
        finally:
            lock.unlink(missing_ok=True)

    def generate(self,**args):
        voice=args.pop('voice',None)
        if voice is not None:
            if 'reference_audio' in args:
                raise ValueError('Choose voice OR reference_audio, not both')
            registry=self.voice_registry()
            if not isinstance(voice,str) or voice not in registry:
                raise ValueError(f'Unknown voice {voice!r}; available: {list(registry)}. Call indextts_references.')
            args['reference_audio']=audio_path(str(self.voice_path(registry[voice])))
        params=validate(args,self.config)
        return self.request('/jobs',params)

    def job(self,job_id):
        if not isinstance(job_id,str) or len(job_id)!=32 or any(c not in '0123456789abcdef' for c in job_id):
            raise ValueError('job_id must be the 32-character ID returned by generate')
        file=self.state/'jobs'/(job_id+'.json')
        job=read_json(file)
        if job['status'] in ('queued','running'):
            if not self.status()['online']:
                return {**job,'backend_offline':True,'next_step':'Inspect backend.log; generation may have been interrupted. Restart recovers stale jobs as failed.'}
            job['elapsed_seconds']=round(time.time()-job.get('started_at',job['created_at']),3)
        if job['status']=='succeeded':
            output=Path(job['audio']['path']).resolve()
            if output.parent!=(self.home/'outputs').resolve():
                raise ValueError('Output outside configured output directory')
            job['audio']=wav_info(output)
        return job

    def stop(self):
        result=self.request('/stop',{})
        (self.state/'launch.json').unlink(missing_ok=True)
        return result


def schema(properties=None,required=None):
    return {'type':'object','properties':properties or {},'required':required or [],'additionalProperties':False}


TEXT={'type':'string'}
GENERATE={
 'text':{'type':'string','minLength':1,'maxLength':5000},
 'voice':{'type':'string','description':'Registered voice name, e.g. 哈基米. Discover names with indextts_references. Choose voice OR reference_audio.'},
 'reference_audio':{'type':'string','description':'Absolute local speaker-reference audio path, alternatively use voice=<registered name>'},
 'language':{'type':'string','enum':LANGUAGES,'default':'ZH'},
 'duration_factor':{'type':'number','minimum':.5,'maximum':2,'default':1,'description':'Approximate duration multiplier. Larger is slower; does not guarantee exact duration.'},
 'emotion_audio':{'type':'string','description':'Absolute local emotion-reference path, mutually exclusive with vector/text'},
 'emotion_vector':{'type':'array','items':{'type':'number','minimum':0,'maximum':1},'minItems':8,'maxItems':8,'description':', '.join(EMOTIONS)},
 'emotion_text':{'type':'string','maxLength':500,'description':'Requires use_qwen_emo=true and more VRAM'},
 'use_emotion_text':{'type':'boolean','default':False,'description':'Infer emotion from the spoken text when no emotion_text is supplied; requires QwenEmotion'},
 'emotion_weight':{'type':'number','minimum':0,'maximum':1,'default':.65},
 'random_emotion':{'type':'boolean','default':False},
 'max_tokens_per_segment':{'type':'integer','minimum':20,'maximum':600,'default':120,'description':'Also checked against the loaded model limit'},
 'temperature':{'type':'number','minimum':.1,'maximum':2,'default':.8},
 'top_p':{'type':'number','minimum':.01,'maximum':1,'default':.8},
 'top_k':{'type':'integer','minimum':0,'maximum':100,'default':30},
 'num_beams':{'type':'integer','minimum':1,'maximum':10,'default':3},
 'do_sample':{'type':'boolean','default':True},
 'length_penalty':{'type':'number','minimum':-2,'maximum':2,'default':0},
 'repetition_penalty':{'type':'number','minimum':.1,'maximum':20,'default':10},
 'max_mel_tokens':{'type':'integer','minimum':50,'maximum':4096,'default':1500,'description':'Output token cap; small values may truncate speech. Checked against actual model config.'},
 'interval_silence_ms':{'type':'integer','minimum':0,'maximum':2000,'default':200,'description':'Silence between model-generated segments in milliseconds'},
 'text_normalization':{'type':'boolean','default':True,'description':'Normalize text before synthesis; keep inline <文字|发音> annotations intact'},
 'seed':{'type':'integer','minimum':0,'maximum':4294967295,'description':'Best-effort reproducibility; GPU kernels may remain nondeterministic'}
}
TOOLS=[
 ('indextts_environment','Inspect local installation, required models, capabilities and status','environment',schema()),
 ('indextts_status','Check model loading phase, failures, queue and active task','status',schema()),
 ('indextts_start','Start hidden local IndexTTS2.5 backend; returns before model loading completes','start',schema()),
 ('indextts_references','List registered named voices and bundled reference WAV files','references',schema()),
 ('indextts_register_voice','Copy a user-selected local reference into the named voice library for later reuse','register_voice',schema({'name':TEXT,'reference_audio':TEXT,'description':TEXT},['name','reference_audio'])),
 ('indextts_generate','Queue local TTS using a named voice or reference audio. Returns job_id; poll indextts_job','generate',{**schema(GENERATE,['text']),'oneOf':[{'required':['voice']},{'required':['reference_audio']}]}),
 ('indextts_job','Read persistent task status and verified WAV metadata','job',schema({'job_id':TEXT},['job_id'])),
 ('indextts_stop','Stop this authenticated backend and free VRAM; refused while loading or jobs exist','stop',schema())
]


def dispatch(bridge,request):
    method=request.get('method')
    if method=='initialize':
        params=request.get('params',{})
        supported=['2024-11-05','2025-03-26','2025-06-18','2025-11-25']
        version=params.get('protocolVersion')
        return {'protocolVersion':version if version in supported else supported[-1],
                'capabilities':{'tools':{'listChanged':False}},'serverInfo':{'name':APP,'version':VERSION}}
    if method=='ping':
        return {}
    if method=='tools/list':
        return {'tools':[{'name':name,'description':desc,'inputSchema':spec} for name,desc,_,spec in TOOLS]}
    if method=='tools/call':
        try:
            params=request.get('params',{})
            name=params['name']; args=params.get('arguments',{})
            tool=next((t for t in TOOLS if t[0]==name),None)
            if tool is None:
                raise ValueError('Unknown tool: '+str(name))
            if not isinstance(args,dict) or set(args)-set(tool[3]['properties']):
                raise ValueError('Invalid/unknown arguments')
            result=getattr(bridge,tool[2])(**args)
            return {'content':[{'type':'text','text':json.dumps(result,ensure_ascii=False)}],'isError':False}
        except Exception as exc:
            return {'content':[{'type':'text','text':f'{type(exc).__name__}: {exc}'}],'isError':True}
    raise LookupError('Method not found')


def main():
    bridge=Bridge()
    for line in sys.stdin:
        request=None
        try:
            request=json.loads(line)
            if not isinstance(request,dict):
                raise ValueError('Expected a JSON-RPC object')
            if 'id' not in request:
                continue
            try:
                result=dispatch(bridge,request)
                response={'jsonrpc':'2.0','id':request['id'],'result':result}
            except LookupError as exc:
                response={'jsonrpc':'2.0','id':request['id'],'error':{'code':-32601,'message':str(exc)}}
        except Exception as exc:
            response={'jsonrpc':'2.0','id':request.get('id') if isinstance(request,dict) else None,
                      'error':{'code':-32700,'message':str(exc)}}
        print(json.dumps(response,ensure_ascii=False),flush=True)


if __name__=='__main__':
    if hasattr(sys.stdout,'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stdin.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser()
    parser.add_argument('--call',choices=[t[0] for t in TOOLS])
    parser.add_argument('--args',default='{}')
    options=parser.parse_args()
    if options.call:
        print(json.dumps(dispatch(Bridge(),{'method':'tools/call','params':{'name':options.call,'arguments':json.loads(options.args)}}),ensure_ascii=False,indent=2))
    else:
        main()
