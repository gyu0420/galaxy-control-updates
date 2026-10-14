"""Check the shipped UI and state transitions without posting real reviews."""
import os, sys, tempfile, time
from pathlib import Path
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

os.environ['QT_QPA_PLATFORM']='offscreen'
sys.path.insert(0,sys.argv[1])
with tempfile.TemporaryDirectory() as tmp:
    os.environ['LOCALAPPDATA']=tmp
    from core import KST
    from professor import countdown_message
    from performance_schedule import PerformanceSchedule
    from reviews import ReviewState, BRANDS, INTERVAL_MS
    import app
    from PySide6.QtWidgets import QApplication, QLabel
    root=Path(sys.argv[1])
    schedule=PerformanceSchedule(root)
    def at(day,h,m,s=0):return datetime(2026,10,day,h,m,s,tzinfo=KST)
    def message(day,h,m,s=0):return countdown_message(now=at(day,h,m,s),schedule=schedule.times(at(day,h,m,s).date().isoformat()))
    assert KST.utcoffset(None)==timedelta(hours=9)
    assert message(14,12,0)=='오늘은 공연이 없는날이야..'
    assert '1시간0분뒤 공연이야!' in message(16,12,0)
    assert '0시간1분뒤 공연이야!' in message(16,12,59,59)
    assert '지금 공연 중' in message(16,13,0)
    assert '1시간0분뒤 공연이야!' in message(16,14,0)
    assert '지금 마지막 공연 중' in message(16,19,0)
    assert '지금 마지막 공연 중' in message(16,19,59,59)
    assert message(16,20,0)=='오늘은 공연이 모두 다 끝났어!'
    assert '10시간0분뒤' in message(17,0,0)
    assert '지금 공연 중' in message(17,10,0)
    assert message(17,19,30)=='오늘은 공연이 모두 다 끝났어!'
    assert '13시간0분뒤' in countdown_message(now=datetime(2026,10,15,15,tzinfo=timezone.utc),schedule=schedule.times('2026-10-16'))
    schedule.observe('2026-10-16',[])
    assert len(schedule.times('2026-10-16'))==4
    schedule.observe('2026-10-16',['오후 9:00'])
    assert schedule.times('2026-10-16')[-1]=='21:00'
    schedule.save(schedule.data['weekly'],60,'2026-10-16',[])
    assert PerformanceSchedule(root).times('2026-10-16')==[]
    schedule.save(schedule.data['weekly'],60,'2026-10-16',clear_override=True)
    print('PASS: KST without zoneinfo/tzdata/pytz, midnight, show boundaries, booking cutoff, cancellations and saved schedules')

    state=ReviewState(Path(tmp)/'review-test.json')
    p='sample'
    assert not state.observe(p,{'ids':['a','b'],'count':2})
    assert state.observe(p,{'ids':['c','a','b'],'count':3})
    assert ReviewState(state.path).unread(p)
    state.acknowledge(p)
    assert not ReviewState(state.path).unread(p)
    assert not state.observe(p,{'ids':['b','c','a'],'count':3})
    assert not state.observe(p,{'ids':['c','b'],'count':2})
    assert state.observe(p,{'ids':['d','c','b'],'count':3})
    try:state.observe(p,{'ids':[],'count':None})
    except ValueError:pass
    else:raise AssertionError('Unreadable review page was accepted')
    assert state.unread(p)
    print('PASS: first-review baseline, new-review detection, persisted n, acknowledgement, reorder/deletion and failure handling')

    qa=QApplication([]);win=app.App(services=False);win.show();qa.processEvents()
    with patch.object(app.QTimer,'singleShot'),patch.object(app.startup,'preference',return_value=True):win.begin_services()
    assert win.review_timer.isActive() and win.review_timer.interval()==INTERVAL_MS==1800000
    calls=[]
    snapshots={place:{'ids':['first-'+place],'count':1} for _,place,_ in BRANDS}
    class Scanner:
        def fetch(self,place):calls.append(place);return snapshots[place]
        def close(self):pass
    def refresh():
        with patch.object(app,'ReviewScanner',Scanner):
            win.check_reviews()
            deadline=time.monotonic()+5
            while win.review_checking and time.monotonic()<deadline:qa.processEvents();win.poll();time.sleep(.01)
            assert not win.review_checking
    refresh();assert set(calls)==set(snapshots)
    assert all(b.isHidden() for b in win.review_badges.values())
    for place in snapshots:snapshots[place]={'ids':['new-'+place,'first-'+place],'count':2}
    refresh();assert all(not b.isHidden() for b in win.review_badges.values())
    for _,place,_ in BRANDS:
        assert win.review_badges[place].text()=='n'
        assert '#e53935' in win.review_badges[place].styleSheet() and 'color:white' in win.review_badges[place].styleSheet()
        with patch.object(app.QDesktopServices,'openUrl',return_value=False):win.open_brand(place)
        assert win.review_state.unread(place)
        with patch.object(app.QDesktopServices,'openUrl',return_value=True):win.review_badges[place].click()
        assert not win.review_state.unread(place) and win.review_badges[place].isHidden()
    with patch.object(app,'today',return_value='2026-10-14'):win.tick()
    assert win.professor.message=='오늘은 공연이 없는날이야..'
    with patch.object(app,'today',return_value='2026-10-16'),patch.object(app,'countdown_message',return_value='다음 공연') as countdown:
        win.tick();assert win.schedule_day=='2026-10-16' and countdown.call_args.kwargs['schedule']
    manifest={'version':'8.41','notes':['공연 안내 개선','리뷰 알림 개선']}
    def inspect_dialog():
        labels=[x.text() for x in win.update_dialog.findChildren(QLabel)]
        assert '업데이트가 있습니다!' in labels
        assert any('공연 안내 개선' in x for x in labels)
        win.update_dialog.reject()
    with patch.object(app.updater,'stage') as stage:
        app.QTimer.singleShot(0,inspect_dialog);win.show_update(manifest);assert not stage.called
    win.close()
    print('PASS: all three brands refresh, actual 30-minute timer, red/white n, click acknowledgement, midnight UI and update notes before approval')
