"""Check tracked source files without importing application or model code."""
import ast
import json
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[1]
paths = subprocess.check_output(['git', '-c', 'safe.directory='+root.as_posix(), 'ls-files', '-z'], cwd=root).decode('utf-8').split('\0')
errors = []
count = 0
for name in filter(None, paths):
    path = root / name
    if path.is_symlink() or not path.is_file():
        continue
    try:
        if path.suffix == '.py':
            ast.parse(path.read_text(encoding='utf-8-sig'), filename=name)
            count += 1
        elif path.suffix == '.json':
            json.loads(path.read_text(encoding='utf-8-sig'))
            count += 1
    except (SyntaxError, ValueError, UnicodeError) as exc:
        errors.append(f'{name}: {exc}')
    if path.name in {'config.json', 'runtime.json', 'auth.json', 'credentials.json', '.env'}:
        errors.append(f'Local-only file tracked: {name}')
    if path.stat().st_size >= 50 * 1024 * 1024:
        errors.append(f'File too large for source repository: {name}')
license_text = (root / 'LICENSE').read_text(encoding='utf-8')
if 'MIT License' not in license_text or 'THE SOFTWARE IS PROVIDED "AS IS"' not in license_text:
    errors.append('Root LICENSE must contain the complete MIT text.')
if errors:
    raise SystemExit('\n'.join(errors))
print(f'Validated {count} Python/JSON files and MIT license.')
