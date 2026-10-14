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
import textwrap
import urllib.request
import zipfile
from pathlib import Path
from unittest.mock import patch

REPO=Path(__file__).resolve().parents[1]
OUTPUT=REPO/'verification-output'
OUTPUT.mkdir(exist_ok=True)
os.environ['QT_QPA_PLATFORM']='offscreen'
BASE_URL='https://raw.githubusercontent.com/gyu0420/galaxy-control-updates/main/'
CANDIDATE=os.environ.get('GALAXY_CANDIDATE')=='1'
reports=[]
def passed(text):
    reports.append(text)
    print('PASS: '+text,flush=True)
def fetch(url):
    with urllib.request.urlopen(url,timeout=30) as response:return response.read()

with tempfile.TemporaryDirectory(prefix='galaxy-update-verification-',ignore_cleanup_errors=True) as tmp:
    tmp=Path(tmp)
    os.environ['LOCALAPPDATA']=str(tmp/'local')
    original=tmp/'original'/'internal';original.mkdir(parents=True)
    with zipfile.ZipFile(REPO/'updates/8.39.zip') as z:z.extractall(original)
    local_manifest=(REPO/'latest.json').read_bytes()
    manifest_raw=local_manifest if CANDIDATE else fetch(BASE_URL+'latest.json')
    assert json.loads(manifest_raw)==json.loads(local_manifest),'Live feed differs from checked-out release'
    envelope=json.loads(manifest_raw)
    manifest=json.loads(base64.b64decode(envelope['payload']))
    assert manifest['version']=='8.41'
    package=(REPO/'updates/8.41.zip').read_bytes() if CANDIDATE else fetch(manifest['url'])
    assert package==(REPO/'updates/8.41.zip').read_bytes()
    assert hashlib.sha256(package).hexdigest()==manifest['sha256']
    passed(('Candidate' if CANDIDATE else 'Live GitHub')+' manifest and complete download match the signed 8.41 release')
    (original/'update_source.json').write_text(json.dumps({'manifest_url':BASE_URL+'latest.json'}))
    sys.path.insert(0,str(original))
    import updater
    assert updater.VERSION=='8.39'
    assert updater.verified_manifest(manifest_raw,original)==manifest
    broken=dict(envelope);broken['signature']=base64.b64encode(bytes(64)).decode()
    try:updater.verified_manifest(json.dumps(broken).encode(),original)
    except Exception:pass
    else:raise AssertionError('Invalid signature accepted')
    assert updater.check(original,fetch=lambda url,limit:manifest_raw)==manifest
    try:updater.stage(original,fetch=lambda url,limit:package[:-1],manifest=manifest)
    except ValueError:pass
    else:raise AssertionError('Damaged package accepted')
    assert not (updater.base_dir()/'pending_update.json').exists()
    passed('Signature rejection, damaged-download rejection, and 8.39 discovery of 8.41')
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
    screenshot=OUTPUT/'restarted-8.41.png'
    (hook/'sitecustomize.py').write_text('import sys\nsys.argv.extend(["--preview",'+repr(str(screenshot))+'])\n')
    os.environ['PYTHONPATH']=str(hook)
    children=[];errors=[]
    real_popen=subprocess.Popen
    def child(*args,**kwargs):
        p=real_popen(*args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,**kwargs)
        children.append(p);return p
    real_stage=updater.stage
    def verified_stage(root,manifest=None):
        if CANDIDATE:return real_stage(root,fetch=lambda url,limit:package,manifest=manifest)
        return real_stage(root,manifest=manifest)
    with patch.object(updater,'stage',side_effect=verified_stage),patch.object(app.subprocess,'Popen',side_effect=child),patch.object(QMessageBox,'warning',side_effect=lambda *args:errors.append(str(args[-1]))):
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
    assert (target/'release_version.txt').read_text().strip()=='8.41'
    assert screenshot.is_file() and screenshot.stat().st_size>1000
    assert not (updater.base_dir()/'pending_update.json').exists()
    for name,data in settings.items():assert json.loads((target/name).read_text())==data,name
    assert (target/'PACKAGE_SHA256').read_text()==manifest['sha256']
    passed('Confirm downloads, stages, and really restarts the shipped Windows app as 8.41')
    passed('Reservation records, settings, crew progress, and chat settings survive the restart')
    feature_check=subprocess.run([sys.executable,str(REPO/'tests/release_feature_check.py'),str(target)],capture_output=True,timeout=45)
    (OUTPUT/'release-features.log').write_bytes(feature_check.stdout+feature_check.stderr)
    assert feature_check.returncode==0,(feature_check.stdout+feature_check.stderr).decode(errors='replace')
    print(feature_check.stdout.decode(errors='replace'),flush=True)
    passed('Shipped 8.41 UI: 30-minute reviews, all-brand n badges and click clearing, update notes, KST and full performance boundaries')
    sys.path.insert(0,str(target))
    import importlib.util
    spec=importlib.util.spec_from_file_location('verified_professor',target/'professor.py')
    professor=importlib.util.module_from_spec(spec);spec.loader.exec_module(professor)
    from performance_schedule import PerformanceSchedule
    from datetime import datetime
    from core import KST
    schedule=PerformanceSchedule(target)
    clock=lambda d,h,m:datetime(2026,10,d,h,m,tzinfo=KST)
    assert professor.countdown_message(now=clock(14,12,0),schedule=schedule.times('2026-10-14'))=='오늘은 공연이 없는날이야..'
    assert '1시간0분뒤 공연이야!' in professor.countdown_message(now=clock(16,12,0),schedule=schedule.times('2026-10-16'))
    assert '지금 마지막 공연 중' in professor.countdown_message(now=clock(16,19,59),schedule=schedule.times('2026-10-16'))
    assert professor.countdown_message(now=clock(16,20,0),schedule=schedule.times('2026-10-16'))=='오늘은 공연이 모두 다 끝났어!'
    schedule.observe('2026-10-16',[]);assert len(schedule.times('2026-10-16'))==4
    schedule.save(schedule.data['weekly'],60,'2026-10-16',[]);assert schedule.times('2026-10-16')==[]
    passed('Professor distinguishes no-show day, countdown, in-progress final show, end at 60 minutes, booking cutoff and special cancellation')
    if sys.platform=='win32':
        ps=['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass']
        registered=subprocess.run(ps+['-File',str(target/'SetStartup.ps1'),'-Enabled','1'],capture_output=True)
        (OUTPUT/'startup-registration.log').write_bytes(registered.stdout+registered.stderr)
        assert registered.returncode==0,(registered.stdout+registered.stderr).decode(errors='replace')
        verify_startup=tmp/'verify-startup.ps1'
        verify_startup.write_text("[Console]::OutputEncoding = [Text.Encoding]::UTF8\n. '"+str(target/'ShortcutNative.ps1').replace("'","''")+"'\n$p=Join-Path ([Environment]::GetFolderPath('Startup')) '갤럭시 관제소.lnk'; if (!(Test-Path -LiteralPath $p)) {exit 4}; [GalaxyShortcutNative]::Read($p)",encoding='utf-8-sig')
        info=subprocess.run(ps+['-File',str(verify_startup)],check=True,capture_output=True,encoding='utf-8')
        assert 'launch.py' in info.stdout
        subprocess.run(ps+['-File',str(target/'SetStartup.ps1'),'-Enabled','0'],check=True,capture_output=True)
        passed('Actual Windows PowerShell creates and removes the startup shortcut')
        # Execute the actual public installer bytes, full shipped launcher and
        # setup.bat. Only sitecustomize adds preview arguments to avoid services.
        installer=REPO/'installers/Galaxy_Control_v8_41_Kakao.zip'
        with zipfile.ZipFile(installer) as outer:
            shipped=outer.read('Galaxy_Control_v8_41.vbs')
        source=shipped.decode('utf-16')
        assert 'WScript.Quit result' in source
        encoded=''.join(line[9:] for line in source.splitlines() if line.startswith("'PAYLOAD "))
        with zipfile.ZipFile(io.BytesIO(base64.b64decode(encoded))) as payload:
            assert payload.testzip() is None
            assert 'internal/team_chat.json' not in payload.namelist()
            with zipfile.ZipFile(io.BytesIO(package)) as update:
                for name in update.namelist():assert payload.read('internal/'+name)==update.read(name),name
        passed('Actual distributed installer payload is valid and identical to signed update; private room excluded')
        fresh=tmp/'fresh-local';fresh.mkdir()
        os.environ['LOCALAPPDATA']=str(fresh)
        first_screen=OUTPUT/'installed-8.41.png'
        (hook/'sitecustomize.py').write_text('import sys\nsys.argv.extend(["--preview",'+repr(str(first_screen))+'])\n')
        actual_installer=tmp/'Galaxy_Control_v8_41.vbs';actual_installer.write_bytes(shipped)
        installed=subprocess.run(['cscript.exe','//nologo',str(actual_installer)],capture_output=True,timeout=60)
        (OUTPUT/'installer-bootstrap.log').write_bytes(installed.stdout+installed.stderr)
        assert installed.returncode==0,(installed.stdout+installed.stderr).decode(errors='replace')
        extracted=updater.base_dir()/'GalaxyControl_v8_41'
        assert (extracted/'.extracted').read_text().strip()=='8.41'
        assert (extracted/'internal/app.py').read_bytes()==(target/'app.py').read_bytes()
        deadline=time.monotonic()+360
        while not first_screen.exists() and time.monotonic()<deadline:time.sleep(.5)
        setup_log=extracted/'setup.log'
        if setup_log.exists():shutil.copyfile(setup_log,OUTPUT/'fresh-setup.log')
        assert first_screen.exists(),'Real installer did not launch app: '+(setup_log.read_text(errors='replace')[-3000:] if setup_log.exists() else 'no setup log')
        assert (fresh/'GRP/env/Scripts/pythonw.exe').exists()
        passed('Actual shipped VBS performs fresh Python environment setup, installs dependencies and really launches 8.41 on Windows')
        def shortcut_script(folder,extra=''):
            script=tmp/'verify-shortcut.ps1'
            script.write_text("[Console]::OutputEncoding = [Text.Encoding]::UTF8\n. '"+str(extracted/'internal/ShortcutNative.ps1').replace("'","''")+"'\n$p=Join-Path ([Environment]::GetFolderPath('"+folder+"')) '갤럭시 관제소.lnk'; if (!(Test-Path -LiteralPath $p)) {exit 4}; [GalaxyShortcutNative]::Read($p); "+extra,encoding='utf-8-sig')
            return subprocess.run(ps+['-File',str(script)],check=True,capture_output=True,encoding='utf-8')
        desktop=shortcut_script('Desktop')
        assert 'GalaxyControl_v8_41' in desktop.stdout and 'robocrew.ico' in desktop.stdout and 'pythonw.exe' in desktop.stdout
        passed('Actual Windows desktop shortcut has the correct Python target, launcher and icon')
        second_screen=OUTPUT/'shortcut-restarted-8.41.png'
        (hook/'sitecustomize.py').write_text('import sys\nsys.argv.extend(["--preview",'+repr(str(second_screen))+'])\n')
        shortcut_script('Desktop','Start-Process -FilePath $p')
        deadline=time.monotonic()+40
        while not second_screen.exists() and time.monotonic()<deadline:time.sleep(.2)
        assert second_screen.exists(),'Desktop shortcut did not relaunch actual app'
        passed('Launching the actual desktop .lnk really restarts installed 8.41')
    win.close()
(OUTPUT/'result.json').write_text(json.dumps({'status':'passed','platform':sys.platform,'checks':reports},ensure_ascii=False,indent=2),encoding='utf-8')
