"""Build a relocatable local marketplace and clean ZIP, excluding all runtime data."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from common import atomic_json, VERSION


def write_launcher(plugin, command, args, env=None):
    """Codex plugin stdio servers must use a bare executable, so absolute paths live in a launcher."""
    def quote(value):
        return '"' + str(value).replace('%', '%%') + '"'
    lines = ['@echo off', 'chcp 65001 >nul']
    lines += ['set "{}={}"'.format(key, str(value).replace('%', '%%')) for key, value in (env or {}).items()]
    lines.append(' '.join(quote(part) for part in [command, *args]))
    (plugin / 'launch-mcp.cmd').write_text('\r\n'.join(lines) + '\r\n', encoding='utf-8')
    return {'type': 'stdio', 'command': 'cmd.exe', 'args': ['/d', '/s', '/c', 'call', './launch-mcp.cmd'], 'cwd': './'}


def build(python=None):
    for name in ('config', 'voices'):
        target=ROOT/(name+'.json')
        if not target.exists():
            shutil.copyfile(ROOT/(name+'.example.json'),target)
    config=json.loads((ROOT/'config.json').read_text(encoding='utf-8-sig'))
    executable=Path(python or Path(config['tts_root'])/'python_embeded/python.exe').resolve()
    if not executable.is_file():
        raise ValueError('Python not found: '+str(executable))
    plugin=ROOT/'plugins/pink-bird-indextts'
    plugin.mkdir(parents=True,exist_ok=True)
    sources=[ROOT/f for f in ('LICENSE','THIRD_PARTY_NOTICES.md','plugin.json','server.py','backend.py','common.py','voices.json')]
    voice_sources=[]
    for entry in json.loads((ROOT/'voices.json').read_text(encoding='utf-8-sig')).values():
        source=(ROOT/entry['path']).resolve()
        if not source.is_relative_to((ROOT/'voices').resolve()) or not source.is_file():
            raise ValueError('Packaged voices must be existing files inside voices/: '+str(source))
        voice_sources.append(source)
    sources+=voice_sources
    for directory in ('skills','assets'):
        sources += [p for p in (ROOT/directory).rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    for source in sources:
        target=plugin/source.relative_to(ROOT)
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,target)
    atomic_json(plugin/'mcp.json',{
        '$schema':'https://agent-plugins.org/schemas/1.0.0/mcp.schema.json',
        'mcpServers':{'indextts':write_launcher(plugin,executable,['-u',str(plugin/'server.py')],
          {'INDEXTTS_MCP_HOME':str(ROOT),'PYTHONUTF8':'1'})}})
    atomic_json(ROOT/'.agents/plugins/marketplace.json',{
        'name':'pink-bird-local','interface':{'displayName':'粉红小鸟 · 本地语音'},
        'plugins':[{'name':'pink-bird-indextts','source':{'source':'local','path':'./plugins/pink-bird-indextts'},
                    'policy':{'installation':'AVAILABLE','authentication':'ON_INSTALL'},'category':'Creativity'}]})
    plugin_files=[plugin/p.relative_to(ROOT) for p in sources]+[plugin/'mcp.json',plugin/'launch-mcp.cmd']
    hashes={p.relative_to(plugin).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(plugin_files)}
    atomic_json(plugin/'build-info.json',{'version':VERSION,'files':hashes})
    files=[ROOT/f for f in ('LICENSE','THIRD_PARTY_NOTICES.md','voices.example.json','config.example.json','plugin.json','server.py','backend.py','common.py','voices.json','config.json','install-plugin.ps1','README.md','VALIDATION.md','.gitignore')]
    files+=voice_sources+plugin_files+[plugin/'build-info.json']
    if (ROOT/'evidence/official-review.md').is_file():
        files.append(ROOT/'evidence/official-review.md')
    for directory in ('scripts','skills','assets','tests','.agents/plugins'):
        files += [p for p in (ROOT/directory).rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    # Include only explicitly registered plugin voices, never generated outputs or runtime state.
    dist=ROOT/'dist'; dist.mkdir(exist_ok=True)
    archive=dist/f'pink-bird-indextts-plugin-{VERSION}.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(set(files)):
            info=zipfile.ZipInfo('indextts-mcp/'+path.relative_to(ROOT).as_posix(),date_time=(2026,1,1,0,0,0))
            info.compress_type=zipfile.ZIP_DEFLATED
            info.external_attr=0o644<<16
            bundle.writestr(info,path.read_bytes())
    digest=hashlib.sha256(archive.read_bytes()).hexdigest()
    (dist/(archive.name+'.sha256')).write_text(digest+'  '+archive.name+'\n',encoding='ascii')
    return {'plugin':str(plugin),'archive':str(archive),'sha256':digest}


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--python')
    args=parser.parse_args()
    print(json.dumps(build(args.python),ensure_ascii=False,indent=2))
