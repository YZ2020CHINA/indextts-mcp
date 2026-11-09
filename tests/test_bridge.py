import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
import wave
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from common import atomic_json, validate, wav_info, inference_kwargs, sampling_switch_supported
from server import Bridge, dispatch
from backend import Engine

ROOT=Path(__file__).resolve().parents[1]


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.home=Path(self.tmp.name)
        self.config={'tts_root':str(self.home),'port':17866,'use_qwen_emo':False,'max_queue':1}
        atomic_json(self.home/'config.json',self.config)
        self.audio=self.home/'reference.wav'
        with wave.open(str(self.audio),'wb') as output:
            output.setnchannels(1); output.setsampwidth(2); output.setframerate(22050)
            output.writeframes(b'\x00\x00'*2205)
        self.args={'text':'你好','reference_audio':str(self.audio)}

    def tearDown(self):
        self.tmp.cleanup()

    def test_real_stdio_handshake(self):
        env=os.environ.copy(); env['INDEXTTS_MCP_HOME']=str(self.home); env['PYTHONUTF8']='1'
        requests=[{'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-06-18'}},
                  {'jsonrpc':'2.0','method':'notifications/initialized'},
                  {'jsonrpc':'2.0','id':2,'method':'tools/list'},
                  {'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'indextts_generate','arguments':{'text':''}}},
                  {'jsonrpc':'2.0','id':4,'method':'does-not-exist'}]
        process=subprocess.run([sys.executable,str(ROOT/'server.py')],input='\n'.join(json.dumps(r) for r in requests)+'\n',
                               text=True,encoding='utf-8',capture_output=True,env=env,timeout=10)
        self.assertEqual(process.returncode,0,process.stderr)
        replies=[json.loads(line) for line in process.stdout.splitlines()]
        self.assertEqual([r['id'] for r in replies],[1,2,3,4])
        self.assertEqual(replies[0]['result']['protocolVersion'],'2025-06-18')
        self.assertEqual(len(replies[1]['result']['tools']),8)
        self.assertTrue(replies[2]['result']['isError'])
        self.assertEqual(replies[3]['error']['code'],-32601)

    def test_invalid_parameters(self):
        for extra in ({'duration_factor':float('nan')},{'duration_factor':True},{'language':'FR'},
                      {'top_k':1.5},{'emotion_vector':[0]*7},{'emotion_vector':[0]*8,'emotion_audio':str(self.audio)},
                      {'emotion_text':'高兴'},{'reference_audio':'relative.wav'},{'text':''},{'surprise':True}):
            with self.subTest(extra=extra),self.assertRaises((ValueError,TypeError)):
                validate({**self.args,**extra},self.config)
        self.assertEqual(validate(self.args,self.config)['language'],'ZH')

    def test_queue_and_restart_recovery(self):
        engine=Engine(self.home,'token')
        with self.assertRaises(ValueError):
            engine.submit(self.args)
        engine.phase='ready'
        first=engine.submit(self.args)
        with self.assertRaises(ValueError):
            engine.submit(self.args)
        self.assertEqual(len(list((self.home/'.state/jobs').glob('*.json'))),1)
        Engine(self.home,'token')
        recovered=json.loads((self.home/'.state/jobs'/(first['job_id']+'.json')).read_text(encoding='utf-8'))
        self.assertEqual(recovered['status'],'failed')

    def test_unique_concurrent_submissions(self):
        self.config['max_queue']=4; atomic_json(self.home/'config.json',self.config)
        engine=Engine(self.home,'token'); engine.phase='ready'
        results=[]
        threads=[threading.Thread(target=lambda:results.append(engine.submit(self.args))) for _ in range(4)]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        self.assertEqual(len({j['job_id'] for j in results}),4)
        self.assertEqual(engine.queue.qsize(),4)

    def test_wav_and_job_path_boundary(self):
        self.assertEqual(wav_info(self.audio)['duration_seconds'],.1)
        bridge=Bridge(self.home)
        with self.assertRaises(ValueError): bridge.job('../config')
        ident='a'*32
        atomic_json(self.home/'.state/jobs'/(ident+'.json'),{'status':'succeeded','audio':{'path':str(self.audio)}})
        with self.assertRaises(ValueError): bridge.job(ident)

    def test_occupied_port_does_not_rotate_token(self):
        import socket
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0)); sock.listen()
            self.config['port']=sock.getsockname()[1]; atomic_json(self.home/'config.json',self.config)
            self.home.joinpath('python_embeded').mkdir()
            self.home.joinpath('python_embeded/python.exe').touch()
            models=self.home/'checkpoints'; models.mkdir()
            for name in ['config.yaml','gpt.pth','s2mel.pth','codec.pth','multilingual_zh_ja_yue_char_del.tiktoken','wav2vec2bert_stats.pt']:
                (models/name).touch()
            self.home.joinpath('.state').mkdir()
            token=self.home/'.state/token'; token.write_text('original')
            # The unauthenticated socket need not answer HTTP; avoid the normal status probe timeout.
            bridge=Bridge(self.home); bridge.status=lambda:{'online':False}
            with self.assertRaisesRegex(ValueError,'occupied'): bridge.start()
            self.assertEqual(token.read_text(),'original')

    def test_unknown_tool_is_tool_error(self):
        result=dispatch(Bridge(self.home),{'method':'tools/call','params':{'name':'unknown'}})
        self.assertTrue(result['isError'])

    def test_named_voice_discovery_and_resolution(self):
        atomic_json(self.home/'voices.json',{'哈基米':{'path':'reference.wav','description':'用户音色'}})
        bridge=Bridge(self.home)
        self.assertEqual(bridge.references()['voices'][0]['name'],'哈基米')
        self.assertTrue(bridge.references()['voices'][0]['exists'])
        bridge.request=lambda path,data=None:data
        result=bridge.generate(text='今天也是美好的一天',voice='哈基米')
        self.assertEqual(result['reference_audio'],str(self.audio.resolve()))
        self.assertNotIn('voice',result)
        with self.assertRaisesRegex(ValueError,'Unknown voice'):
            bridge.generate(text='你好',voice='不存在')
        with self.assertRaisesRegex(ValueError,'OR'):
            bridge.generate(**self.args,voice='哈基米')
        self.audio.unlink()
        with self.assertRaises(FileNotFoundError):
            bridge.generate(text='你好',voice='哈基米')

    def test_webui_presets_and_name_priority(self):
        folder=self.home/'outputs/presets/新音色'; folder.mkdir(parents=True)
        import shutil
        shutil.copyfile(self.audio,folder/'prompt.wav')
        atomic_json(folder/'preset.json',{'prompt_audio':'prompt.wav','emo_control_method':3})
        bridge=Bridge(self.home)
        self.assertEqual(bridge.references()['voices'][0]['source_type'],'webui_preset')
        bridge.request=lambda path,data=None:data
        self.assertEqual(bridge.generate(text='你好',voice='新音色')['reference_audio'],str((folder/'prompt.wav').resolve()))
        # Selecting an audio by name does not silently enable the preset's Qwen mode.
        self.assertFalse(bridge.generate(text='你好',voice='新音色')['use_emotion_text'])
        atomic_json(self.home/'voices.json',{'新音色':{'path':'reference.wav'}})
        self.assertEqual(bridge.generate(text='你好',voice='新音色')['reference_audio'],str(self.audio.resolve()))
        atomic_json(folder/'preset.json',{'prompt_audio':'../../../reference.wav'})
        self.assertTrue(bridge.references()['warnings'])

    def test_voice_registration_copies_and_prevents_overwrite(self):
        bridge=Bridge(self.home)
        registered=bridge.register_voice('新声音',str(self.audio),'测试')
        copied=Path(registered['path'])
        self.assertEqual(copied.read_bytes(),self.audio.read_bytes())
        self.audio.unlink()
        bridge.request=lambda path,data=None:data
        self.assertEqual(bridge.generate(text='你好',voice='新声音')['reference_audio'],str(copied))
        with self.assertRaisesRegex(ValueError,'already exists'):
            bridge.register_voice('新声音',str(copied))
        self.assertEqual(len(list((self.home/'voices').iterdir())),1)

    def test_upstream_parameter_mapping_and_emotion_modes(self):
        class Model:
            def normalize_emo_vec(self,vec,apply_bias):
                assert apply_bias
                return [v/2 for v in vec]
        cfg={**self.config,'use_qwen_emo':True}
        params=validate({**self.args,'use_emotion_text':True,'interval_silence_ms':350,
                         'do_sample':False,'text_normalization':False,'max_mel_tokens':1600,
                         'repetition_penalty':8.,'length_penalty':.5,'top_k':0},cfg)
        kwargs=inference_kwargs(params,'output.wav',Model())
        self.assertTrue(kwargs['use_emo_text']); self.assertIsNone(kwargs['emo_text'])
        self.assertEqual(kwargs['interval_silence'],350)
        self.assertFalse(kwargs['do_sample']); self.assertFalse(kwargs['text_normalization'])
        self.assertEqual(kwargs['max_mel_tokens'],1600); self.assertIsNone(kwargs['top_k'])
        self.assertEqual(kwargs['repetition_penalty'],8.)
        for extra in ({'emotion_audio':str(self.audio),'use_emotion_text':True},
                      {'emotion_vector':[0]*8,'emotion_text':'平静'}, {'emotion_text':0},
                      {'text_normalization':1},{'max_mel_tokens':True}):
            with self.subTest(extra=extra),self.assertRaises(ValueError):
                validate({**self.args,**extra},cfg)
        vec=validate({**self.args,'emotion_vector':[0,0,0,0,0,0,0,.8]},cfg)
        self.assertEqual(inference_kwargs(vec,'output.wav',Model())['emo_vector'][-1],.4)

    def test_stage_progress_and_runtime_limits(self):
        engine=Engine(self.home,'token'); engine.phase='ready'
        engine.runtime={'max_mel_tokens':1815,'max_text_tokens':600}
        with self.assertRaisesRegex(ValueError,'model limit'):
            engine.submit({**self.args,'max_mel_tokens':1900})
        job=engine.submit(self.args)
        engine.active=job['job_id']
        engine.report_progress(.2,'speech synthesis 1/2')
        bridge=Bridge(self.home); bridge.status=lambda:{'online':True}
        current=bridge.job(job['job_id'])
        self.assertEqual(current['progress'],.2)
        self.assertEqual(current['stage'],'speech synthesis 1/2')
        self.assertGreaterEqual(current['elapsed_seconds'],0)

    def test_installed_sampling_switch_detection(self):
        path=self.home/'infer.py'
        path.write_text('model.inference_speech(do_sample=True)',encoding='utf-8')
        self.assertFalse(sampling_switch_supported(path))
        path.write_text('model.inference_speech(do_sample=do_sample)',encoding='utf-8')
        self.assertTrue(sampling_switch_supported(path))
        engine=Engine(self.home,'token'); engine.phase='ready'
        engine.runtime={'sampling_switch_supported':False}
        with self.assertRaisesRegex(ValueError,'hardcodes'):
            engine.submit({**self.args,'do_sample':False})


if __name__=='__main__':
    unittest.main()
