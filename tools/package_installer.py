"""Build a VBS installer from the same source as the signed update archive.

Usage: python tools/package_installer.py SOURCE VERSION OUTPUT [--private-room]
The public build omits employee room credentials and personal state.
"""
import base64
import io
import re
import sys
import textwrap
import zipfile
from pathlib import Path

root, version, output = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
assert re.fullmatch(r'\d+\.\d+(?:\.\d+)?', version)
assert (root / 'internal/release_version.txt').read_text().strip() == version
private_room = '--private-room' in sys.argv[4:]
excluded = {'reservation_history.json', 'settings.json', 'crew_progress.json',
            'chat_settings.json', 'review_state.json', 'performance_schedule.json',
            'startup_preference.json', 'signing_key.pem'}
if not private_room:
    excluded.add('team_chat.json')
buffer = io.BytesIO()
with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
    for path in sorted(root.rglob('*')):
        if path.is_file() and path.name not in excluded and '__pycache__' not in path.parts and path.suffix not in ('.pyc', '.log'):
            archive.write(path, path.relative_to(root))
payload = buffer.getvalue()
with zipfile.ZipFile(io.BytesIO(payload)) as archive:
    assert archive.testzip() is None
header = (Path(__file__).resolve().parents[1] / 'tests/installer_header.vbs').read_text(encoding='utf-8')
assert 'WScript.Quit result' in header
header = re.sub(r'GalaxyControl_v[0-9_]+', 'GalaxyControl_v' + version.replace('.', '_'), header)
header = re.sub(r"-Value '\d+\.\d+(?:\.\d+)?'", "-Value '" + version + "'", header)
# Select entire non-payload lines: splitting at the literal PAYLOAD marker
# also splits its occurrence inside the bootstrap code and corrupts the file.
lines = textwrap.wrap(base64.b64encode(payload).decode(), 120)
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(header + ''.join("'PAYLOAD " + line + '\n' for line in lines), encoding='utf-16')
decoded = base64.b64decode(''.join(line[9:] for line in output.read_text(encoding='utf-16').splitlines() if line.startswith("'PAYLOAD ")))
assert decoded == payload
with zipfile.ZipFile(output.with_name(output.stem + '_Kakao.zip'), 'w', zipfile.ZIP_DEFLATED) as archive:
    archive.write(output, output.name)
print('PASS: complete installer bootstrap and valid ZIP payload; private room: ' + str(private_room))
