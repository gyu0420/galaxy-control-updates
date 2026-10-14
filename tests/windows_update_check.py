"""Exercise shipped update archives on Windows, including a real child launch."""
import base64
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path
from unittest.mock import patch

REPO=Path(__file__).resolve().parents[1]
OUTPUT=REPO/'verification-output'
OUTPUT.mkdir(exist_ok=True)
os.environ['QT_QPA_PLATFORM']='offscreen'
BASE_URL='https://raw.githubusercontent.com/gyu0420/galaxy-control-updates/main/'
reports=[]
def passed(text):
    reports.append(text)
    print('PASS: '+text,flush=True)
def fetch(url):
    with urllib.request.urlopen(url,timeout=30) as response:return response.read()

with tempfile.TemporaryDirectory(prefix='galaxy-update-verification-') as tmp:
    tmp=Path(tmp)
    os.environ['LOCALAPPDATA']=str(tmp/'local')
    original=tmp/'original'/'internal';original.mkdir(parents=True)
    with zipfile.ZipFile(REPO/'updates/8.39.zip') as z:z.extractall(original)
    manifest_raw=fetch(BASE_URL+'latest.json')
    local_manifest=(REPO/'latest.json').read_bytes()
    assert json.loads(manifest_raw)==json.loads(local_manifest),'Live feed differs from checked-out release'
    envelope=json.loads(manifest_raw)
    manifest=json.loads(base64.b64decode(envelope['payload']))
    assert manifest['version']=='8.40'
    package=fetch(manifest['url'])
    assert package==(REPO/'updates/8.40.zip').read_bytes()
    assert hashlib.sha256(package).hexdigest()==manifest['sha256']
    passed('Live GitHub manifest and complete download match the signed 8.40 release')
    (original/'update_source.json').write_text(json.dumps({'manifest_url':BASE_URL+'latest.json'}))
    sys.path.insert(0,str(original))
    import updater
    assert updater.VERSION=='8.39'
    assert updater.verified_manifest(manifest_raw,original)==manifest
    broken=dict(envelope);broken['signature']=base64.b64encode(bytes(64)).decode()
    try:updater.verified_manifest(json.dumps(broken).encode(),original)
    except Exception:pass
    else:raise AssertionError('Invalid signature accepted')
    assert updater.check(original)==manifest
    try:updater.stage(original,fetch=lambda url,limit:package[:-1],manifest=manifest)
    except ValueError:pass
    else:raise AssertionError('Damaged package accepted')
    assert not (updater.base_dir()/'pending_update.json').exists()
    passed('Signature rejection, damaged-download rejection, and 8.39 discovery of 8.40')
    settings={'reservation_history.json':{'sentinel':'reservations'},'settings.json':{'sentinel':'settings'},'crew_progress.json':{'sentinel':'crew'},'chat_settings.json':{'code':'','name':'Windows test','auto':False}}
    for name,data in settings.items():(original/name).write_text(json.dumps(data))
    from PySide6.QtWidgets import QApplication,QMessageBox
    from PySide6.QtCore import QTimer
    import app
    qa=QApplication([]);app.load_pixel_fonts();qa.setStyle('Fusion');qa.setStyleSheet(app.STYLE);qa.setFont(app.pixel_font())
    # Avoid parsing artificial reservation-history fixtures in the UI constructor.
    reservation=(original/'reservation_history.json').read_bytes()
    (original/'reservation_history.json').unlink()
    win=app.App(services=False);win.show();qa.processEvents()
    (original/'reservation_history.json').write_bytes(reservation)
    with patch.object(updater,'stage') as stage:
        QTimer.singleShot(0,lambda:win.update_dialog.reject())
        win.show_update(manifest)
        assert not stage.called
    assert not (updater.base_dir()/'pending_update.json').exists()
    passed('Clicking Later neither downloads nor schedules installation')
    # This hook changes only test-process arguments. Both launch.py and app.py
    # remain byte-for-byte the shipped code; preview mode exits after rendering.
    hook=tmp/'hook';hook.mkdir()
    screenshot=OUTPUT/'restarted-8.40.png'
    (hook/'sitecustomize.py').write_text('import sys\nsys.argv.extend(["--preview",'+repr(str(screenshot))+'])\n')
    os.environ['PYTHONPATH']=str(hook)
    children=[];errors=[]
    real_popen=subprocess.Popen
    def child(*args,**kwargs):
        p=real_popen(*args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,**kwargs)
        children.append(p);return p
    with patch.object(app.subprocess,'Popen',side_effect=child),patch.object(QMessageBox,'warning',side_effect=lambda *args:errors.append(str(args[-1]))):
        QTimer.singleShot(0,lambda:win.update_dialog.accept())
        win.show_update(manifest)
        deadline=time.monotonic()+90
        while time.monotonic()<deadline and not children and not errors:
            qa.processEvents();time.sleep(.03)
        assert not errors,errors
        assert len(children)==1,'Automatic relaunch did not start'
        out,err=children[0].communicate(timeout=40)
        (OUTPUT/'relaunch.log').write_bytes(out+err)
        assert children[0].returncode==0,(out+err).decode(errors='replace')
    active=json.loads((updater.base_dir()/'active_update.json').read_text())
    target=Path(active['path'])
    assert (target/'release_version.txt').read_text().strip()=='8.40'
    assert screenshot.is_file() and screenshot.stat().st_size>1000
    assert not (updater.base_dir()/'pending_update.json').exists()
    for name,data in settings.items():assert json.loads((target/name).read_text())==data,name
    assert (target/'PACKAGE_SHA256').read_text()==manifest['sha256']
    passed('Confirm downloads, stages, and really restarts the shipped Windows app as 8.40')
    passed('Reservation records, settings, crew progress, and chat settings survive the restart')
    if sys.platform=='win32':
        ps=['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass']
        subprocess.run(ps+['-File',str(target/'SetStartup.ps1'),'-Enabled','1'],check=True,capture_output=True)
        info=subprocess.run(ps+['-Command',"$s=New-Object -ComObject WScript.Shell; $p=Join-Path ([Environment]::GetFolderPath('Startup')) '갤럭시 관제소.lnk'; $l=$s.CreateShortcut($p); if (!(Test-Path -LiteralPath $p)) {exit 4}; Write-Output $l.Arguments"],check=True,capture_output=True,text=True)
        assert 'launch.py' in info.stdout
        subprocess.run(ps+['-File',str(target/'SetStartup.ps1'),'-Enabled','0'],check=True,capture_output=True)
        passed('Actual Windows PowerShell creates and removes the startup shortcut')
    win.close()
(OUTPUT/'result.json').write_text(json.dumps({'status':'passed','platform':sys.platform,'checks':reports},ensure_ascii=False,indent=2),encoding='utf-8')
