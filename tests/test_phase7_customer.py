import time,math
import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QScrollArea
from zee.core import Store,Device
from zee.gui import Window,DeviceDialog
from zee.workspaces import NetworkPage
from zee.customer_view import wan_view,rate
from zee.customer_theme import status_color,splash_pixmap

@pytest.fixture
def app():return QApplication.instance() or QApplication([])

@pytest.mark.parametrize('value',[None,True,-1,float('nan'),float('inf'),'12'])
def test_unavailable_rates_are_never_zero_or_fabricated(value):assert rate({'download_mbps':value},'download_mbps')=='Unavailable'

def test_wan_card_separates_ping_live_and_checked_test_freshness():
    d=Device(name='WAN',wan=1);now=1000
    v=wan_view(d,'Online',{}, {'at':now,'download_mbps':100},now)
    assert v['router']=='Online' and 'Unknown' in v['internet'] and v['test_download']=='Unavailable'
    v=wan_view(d,'Online',{'at':now,'internet':'Offline','download_mbps':7,'upload_mbps':2},{'at':now,'path_checked':True,'download_mbps':90,'upload_mbps':15},now)
    assert v['internet']=='Offline' and (v['download'],v['test_download'])==('7.00','90.00')
    v=wan_view(d,'Unknown',{'at':1,'internet':'Online','download_mbps':7},{'at':1,'path_checked':True,'download_mbps':90},now)
    assert v['download']==v['test_download']=='Unavailable' and 'old result' in v['test_age']

def test_simple_overview_shortcuts_and_actual_wan_selection(app,tmp_path):
    s=Store(tmp_path/'db');s.set_setting('auto_cleanup',False)
    ds=[Device(name=f'Internet {i}',host=f'127.0.0.{i+1}',wan=i+1) for i in range(7)]
    for d in ds:s.save(d)
    w=Window(s);w.show();app.processEvents()
    try:
        assert w.tabs.currentIndex()==8 and not w.advanced_box.isChecked()
        assert w.nav_buttons[6].isHidden() and w.path_button.isHidden()
        card=w.overview.wan_cards[3];card.open_button.click();app.processEvents()
        assert w.tabs.currentIndex()==7 and w.seven_wan.device().id==ds[3].id
        QTest.keyClick(w,Qt.Key_1,Qt.ControlModifier);app.processEvents();assert w.tabs.currentIndex()==8
        QTest.keyClick(w,Qt.Key_F,Qt.ControlModifier);app.processEvents();assert w.tabs.currentIndex()==1 and w.search.hasFocus()
        w.advanced_box.setChecked(True);assert not w.nav_buttons[6].isHidden() and not w.path_button.isHidden()
    finally:w.close()

def test_theme_and_control_preferences_persist_restart(app,tmp_path):
    path=tmp_path/'db';s=Store(path);s.set_setting('auto_cleanup',False);w=Window(s)
    w.theme_picker.setCurrentIndex(1);w.advanced_box.setChecked(True)
    assert s.setting('ui_theme')=='light' and s.setting('advanced_ui') is True
    assert w.advanced_setting.isChecked();w.close()
    w=Window(Store(path))
    try:assert w.ui_theme=='light' and w.theme_picker.currentData()=='light' and w.advanced_box.isChecked()
    finally:w.close()

def test_basic_device_edit_retains_advanced_settings(app):
    d=Device(name='Existing',host='192.0.2.1',source='192.0.2.50',timeout=3500,management_url='https://192.0.2.1/',map_x=.3,map_y=.7)
    dialog=DeviceDialog([],d)
    try:
        assert dialog.fields['source'].isHidden()
        dialog.fields['name'].setText('Renamed');saved=dialog.device()
        assert saved.source==d.source and saved.timeout==3500 and (saved.map_x,saved.map_y)==(.3,.7) and saved.management_url==d.management_url
        dialog.advanced.setChecked(True);assert not dialog.fields['source'].isHidden()
    finally:dialog.close()

def test_overview_scope_stale_state_and_incidents(app,tmp_path):
    s=Store(tmp_path/'db');s.set_setting('auto_cleanup',False);s.save_page(NetworkPage(id='other',name='Other'))
    a=Device(name='Local WAN',host='127.0.0.1',wan=1);b=Device(name='Other WAN',host='127.0.0.2',wan=2,page_id='other');s.save(a);s.save(b);w=Window(s)
    try:
        w.monitor_all_box.setChecked(True);w.states[a.id]='Online';w.states[b.id]='Online'
        w.latest[a.id]={'at':time.time()-1000,'success':True,'latency':2};w.overview.refresh()
        assert w.overview.metrics[0][1].text()=='1' and w.overview.metrics[1][1].text()=='0'
        assert w.overview.wan_cards[0].id==a.id and w.overview.wan_cards[1].isHidden()
        assert 'selected network' in w.overview.scope.text()
        outcome={'page_id':a.page_id,'device':a.id,'context':'fixture','category':'icmp','status':'active','at':time.time(),'title':'No reply observed','name':a.name,'confidence':'Low','next_step':'Verify the route','evidence':['Two missed checks']}
        s.observe_incidents([outcome]);w.overview.refresh()
        assert '1 unresolved' in w.overview.incident_count.text() and 'No reply observed' in w.overview.incident_text.text()
        s.edit_incident(s.incident_rows()[0]['id'],acknowledged=True);w.overview.refresh();assert 'Acknowledged' in w.overview.incident_text.text()
    finally:w.close()

def test_overview_empty_and_pagination_bounded_database_reads(app,tmp_path):
    s=Store(tmp_path/'db');s.set_setting('auto_cleanup',False);w=Window(s)
    try:
        assert not w.overview.setup.isHidden() and not w.overview.no_wans.isHidden()
        for i in range(20):s.save(Device(name=f'WAN{i}',host='127.0.0.1',wan=i+1))
        w.reload();queries=[];s.db.set_trace_callback(queries.append);w.overview.refresh();s.db.set_trace_callback(None)
        assert len(w.overview.wan_cards)==7 and w.overview.table.rowCount()==8
        assert not any('FROM samples' in q or 'FROM measurements' in q for q in queries)
        ids={d.id for d in w.devices[7:14]};w.overview.move_wans(1);assert {c.id for c in w.overview.wan_cards}==ids
    finally:w.close()

def test_responsive_overview_and_scrollable_forms(app,tmp_path):
    s=Store(tmp_path/'db');s.set_setting('auto_cleanup',False);w=Window(s);w.show()
    try:
        w.resize(1360,790);app.processEvents();assert w.overview._columns==3
        w.resize(980,650);app.processEvents();assert w.overview._columns==2
        w.advanced_box.setChecked(True);app.processEvents();assert w.nav_scroll.verticalScrollBar().maximum()>0
        from zee.professional import IntegrationDialog,DeviceDetails
        d=Device(name='Test',host='127.0.0.1');s.save(d);w.reload()
        for cls in (IntegrationDialog,DeviceDetails):
            dialog=cls(w,d);assert dialog.findChild(QScrollArea) is not None;dialog.close()
    finally:w.close()

def test_splash_and_light_status_contrast(app):
    pix=splash_pixmap('test',1.5);assert pix.devicePixelRatio()==1.5 and pix.width()==930
    def luminance(hexcolor):
        channels=[int(hexcolor[i:i+2],16)/255 for i in (1,3,5)]
        values=[c/12.92 if c<=.04045 else ((c+.055)/1.055)**2.4 for c in channels]
        return sum(a*b for a,b in zip(values,[.2126,.7152,.0722]))
    for state in ('Online','Warning','No reply','Unknown','Checking'):
        assert 1.05/(luminance(status_color(state,'light'))+.05)>=4.5
