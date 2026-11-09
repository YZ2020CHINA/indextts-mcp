"""Exercise the installed MCP command, not an imported bridge object."""
import json
import os
from pathlib import Path
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from common import atomic_json, VERSION

root=Path(__file__).resolve().parents[1]
codex_home=Path(os.environ.get('CODEX_HOME',Path.home()/'.codex'))
installed=codex_home/'plugins/cache/pink-bird-local/pink-bird-indextts'/VERSION
spec=json.loads((installed/'mcp.json').read_text(encoding='utf-8'))['mcpServers']['indextts']
config=json.loads((root/'config.json').read_text(encoding='utf-8'))
env=os.environ.copy(); env.update(spec['env'])
requests=[{'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-06-18'}},
          {'jsonrpc':'2.0','method':'notifications/initialized'},
          {'jsonrpc':'2.0','id':2,'method':'tools/list'},
          {'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'indextts_generate','arguments':{
              'text':'愿你今天拥有平静而美好的心情。','reference_audio':str(Path(config['tts_root'])/'examples/voice_01.wav'),
              'emotion_vector':[0,0,0,0,0,0,0,.7],'num_beams':1,'seed':123}}}]
result=subprocess.run([spec['command'],*spec['args']],input='\n'.join(json.dumps(r,ensure_ascii=False) for r in requests)+'\n',
                      text=True,encoding='utf-8',capture_output=True,env=env,timeout=15)
replies=[json.loads(line) for line in result.stdout.splitlines()]
assert result.returncode==0,result.stderr
assert len(replies[1]['result']['tools'])==8
assert not replies[2]['result']['isError'],replies[2]
job=json.loads(replies[2]['result']['content'][0]['text'])
atomic_json(root/'evidence/installed-mcp.json',{'installed_path':str(installed),'handshake':replies[0],
            'tool_count':len(replies[1]['result']['tools']),'job':job})
print(json.dumps(job,ensure_ascii=False))
