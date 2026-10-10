import json,uuid,ipaddress
from dataclasses import replace
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QInputDialog,QFileDialog,QMessageBox,QDialog
from .workspaces import NetworkPage
from .professional import PageDialog,DeviceDetails
from .connections import management_url
from .ping import probe,Result

class PageControls:
    def current_page(self):return next((p for p in self.store.pages() if p.id==self.page_id),self.store.pages()[0])
    def page_stations(self):return [s for s in self.store.stations() if s.page_id==self.page_id]
    def change_page(self,index):
        id=self.page_picker.itemData(index)
        if not id or id==self.page_id:return
        self._resume_minimized=False
        if self.monitor_all_enabled:
            self.page_id=id;self.store.set_setting('active_page',id);self.reload();return
        self.engine.invalidate();self.measurements.stop();self.requested.clear();self.buzzer.update({});self.page_id=id;self.states.clear();self.latest.clear();self.streaks.clear();self.alerted.clear()
        self.measurements.latest.clear();self.measurements.speed_latest.clear();self.telemetry_alerted.clear()
        self.start_button.setText('▶ Start monitoring');self.store.set_setting('active_page',id);self.reload()
    def monitor_devices(self):
        devices=self.all_devices if self.monitor_all_enabled else self.devices
        return [d for d in devices if self.permit_device(d)] if hasattr(self,'policy') else devices
    def page_for_device(self,d):
        return self.network_pages.get(d.page_id)
    def prepare_network_probe(self,d,fn):
        from .network_paths import prepare_probe
        return prepare_probe(d,self.page_for_device(d),fn,self.monitor_all_enabled,self.monitor_all_enabled and d.id in self.ambiguous_devices)
    def scoped_probe(self,d):
        return probe(d)
    def set_monitor_all(self,enabled):
        self._resume_minimized=False
        self.monitor_all_enabled=enabled;self.store.set_setting('monitor_all',enabled)
        self.engine.invalidate();self.measurements.stop();self.requested.clear()
        self.states.clear();self.latest.clear();self.streaks.clear();self.alerted.clear();self.telemetry_alerted.clear()
        self.measurements.latest.clear();self.measurements.speed_latest.clear()
        self.start_button.setText('▶ Start monitoring');self.reload();self.refresh_map(False)
    def network_setup(self):
        from .network_setup import NetworkSetup
        NetworkSetup(self).exec()
    def connect_radios(self):
        from .network_setup import RadioLinks
        RadioLinks(self).exec()
    def manage_pages(self):
        actions=['Add network','Edit network / routing','Duplicate network','Move page up','Move page down','Archive network','Restore archived network','Delete network','Export network','Import network']
        action,ok=QInputDialog.getItem(self,'Network pages','Action',actions,0,False)
        if not ok:return
        page=self.current_page()
        try:
            if action in actions[:2]:
                p=NetworkPage(id=str(uuid.uuid4()),name='New network',order=len(self.store.pages())) if action==actions[0] else page
                dialog=PageDialog(self,p)
                if dialog.exec()!=QDialog.Accepted:return
                updated=dialog.value()
                if action==actions[1] and (updated.source_ip,updated.interface_hint,updated.gateway_hint)!=(page.source_ip,page.interface_hint,page.gateway_hint):
                    updated=replace(updated,routing_verified=False)
                    for device in self.store.devices():
                        if device.page_id==page.id and device.integration.get('wan_verified'):
                            self.store.save(replace(device,integration=device.integration|{'wan_verified':False}))
                self.store.save_page(updated)
            elif action==actions[2]:self.store.import_page(self.store.export_page(page.id),page.name+' (copy)')
            elif action in actions[3:5]:
                pages=self.store.pages();i=next(i for i,p in enumerate(pages) if p.id==page.id);j=i+(-1 if action==actions[3] else 1)
                if 0<=j<len(pages):pages[i],pages[j]=pages[j],pages[i]
                for order,p in enumerate(pages):self.store.save_page(replace(p,order=order))
            elif action==actions[5]:
                if len([p for p in self.store.pages() if not p.archived])<=1:raise ValueError('Keep at least one active network.')
                self.store.save_page(replace(page,archived=True));self.engine.invalidate();self.measurements.stop()
                self.page_id=next(p.id for p in self.store.pages() if not p.archived)
            elif action==actions[6]:
                pages=[p for p in self.store.pages() if p.archived]
                if not pages:return
                name,ok=QInputDialog.getItem(self,'Restore network','Page',[p.name+' ['+p.id[:8]+']' for p in pages],0,False)
                if ok:self.store.save_page(replace(pages[[p.name+' ['+p.id[:8]+']' for p in pages].index(name)],archived=False))
            elif action==actions[7]:
                if QMessageBox.question(self,'Delete network','Delete this network and its device/tower configuration? History remains; export first if needed.')!=QMessageBox.Yes:return
                if len([p for p in self.store.pages() if not p.archived])<=1:raise ValueError('Keep at least one active network.')
                self.engine.invalidate();self.measurements.stop()
                ids=self.store.delete_page(page.id)
                for id in ids:self.vault.delete(id)
                self.page_id=next(p.id for p in self.store.pages() if not p.archived)
            elif action==actions[8]:
                path,_=QFileDialog.getSaveFileName(self,'Export without secrets','network.json','JSON (*.json)')
                if path:
                    from pathlib import Path
                    Path(path).write_text(json.dumps(self.store.export_page(page.id),indent=2),encoding='utf-8')
            elif action==actions[9]:
                path,_=QFileDialog.getOpenFileName(self,'Import network','','JSON (*.json)')
                if path:
                    from pathlib import Path
                    if Path(path).stat().st_size>10000000:raise ValueError('File too large.')
                    self.store.import_page(json.loads(Path(path).read_text(encoding='utf-8')))
            self.engine.invalidate();self.measurements.stop();self.requested.clear()
            self.measurements.latest.clear();self.measurements.speed_latest.clear();self.telemetry_alerted.clear();self.states.clear();self.latest.clear();self.alerted.clear()
            self.start_button.setText('▶ Start monitoring');self.reload()
        except (ValueError,OSError,KeyError,TypeError) as e:QMessageBox.warning(self,'Network operation failed',str(e))
    def show_details(self,d):
        dialog=DeviceDetails(self,d);self.details_windows.append(dialog);dialog.show()
    def device_double_click(self,*args):
        d=self.selected()
        if d:self.show_details(d);self.open_management(d)
    def open_management(self,d):
        try:
            url=management_url(d)
            if not QDesktopServices.openUrl(QUrl(url)):raise ValueError('No compatible browser is registered.')
        except ValueError as e:QMessageBox.warning(self,'Cannot open device',str(e))
    def restore_database(self):
        path,_=QFileDialog.getOpenFileName(self,'Restore SQLite backup','','SQLite (*.db *.sqlite3 *.bak);;All files (*)')
        if not path:return
        try:
            import sqlite3
            from pathlib import Path
            if Path(path).resolve()==self.store.path.resolve():raise ValueError('Select a different backup file.')
            from .recovery import open_backup
            c=open_backup(path)
            c.close()
            if QMessageBox.question(self,'Restore and restart','Replace current configuration/history on next launch? A safety backup will be kept. Credentials remain on this Windows account.')!=QMessageBox.Yes:return
            import shutil
            shutil.copyfile(path,self.store.path.parent/'restore.pending.sqlite3');self.close()
        except (OSError,ValueError,sqlite3.Error) as e:QMessageBox.warning(self,'Restore failed',str(e))
    def pilot_dialog(self):
        from .pilot_dialog import PilotDialog
        try:PilotDialog(self).exec()
        except Exception:QMessageBox.warning(self,'Pilot evidence unavailable','Could not read pilot evidence. Preserve pilot-evidence.json for support; monitoring configuration was not changed.')
    def license_dialog(self):
        from .system_dialogs import LicenseDialog
        LicenseDialog(self).exec()
    def mobile_dialog(self):
        if hasattr(self,'policy') and not self.policy.allows('mobile'):
            QMessageBox.information(self,'Package permission','Mobile access is not included in this package.');return
        from .system_dialogs import MobileDialog
        MobileDialog(self).exec()
    def update_mobile(self):
        server=getattr(self,'mobile_server',None)
        if not server:return
        if hasattr(self,'policy') and not self.policy.allows('mobile'):server.stop();self.mobile_server=None;return
        import time
        from .telemetry import quality
        from .wan import wan_health
        from .cctv import camera_health
        now=time.time();pages=self.store.pages();names={p.id:p.name for p in pages};towers={s.id:s.name for s in self.store.stations()};devices=[]
        inventory=[d for d in self.store.devices() if any(p.id==d.page_id and not p.archived for p in pages)]
        for d in inventory:
            selected=self.monitor_all_enabled or d.page_id==self.page_id;r=self.measurements.latest.get(d.id,{}) if selected else {};speed=self.measurements.speed_latest.get(d.id,{}) if selected else {};age=now-r.get('at',0);fresh=age<=max(30,d.integration.get('poll_seconds',30)*3)
            speed_fresh=speed and now-speed.get('at',0)<=max(60,d.integration.get('speed_interval',900));rate=speed if speed_fresh else r;rate_fresh=speed_fresh or fresh
            state=self.state(d) if selected else 'Not monitored'
            health=wan_health(d,state,r,speed,now)[0] if d.wan or d.kind.startswith('WAN') else 'Not a WAN'
            service=camera_health(d,r,now) if d.kind.startswith('CCTV') else 'Not a camera'
            devices.append({'id':d.id,'host':d.host,'name':d.name,'page':d.page_id,'network':names.get(d.page_id,''),'tower_id':d.station_id,'tower':towers.get(d.station_id,''),'status':state,'quality':quality(r.get('metrics',{}),d.integration,age)[1],'internet':r.get('internet','Unknown') if fresh else 'Unknown','wan_health':health,'service':service,'download':f"{rate['download_mbps']:.2f} Mbps ({rate.get('rate_kind','measurement')})" if rate_fresh and 'download_mbps' in rate else 'Unavailable','upload':f"{r['upload_mbps']:.2f} Mbps (traffic)" if fresh and 'upload_mbps' in r else 'Unavailable'})
        rows=self.store.events(since=now-86400,limit=100,scope=[d.id for d in inventory])
        server.update({'at':now,'pages':[{'id':p.id,'name':p.name} for p in pages if not p.archived],'devices':devices,'events':[{'device':r['device'],'message':r['message'],'time':time.strftime('%H:%M:%S',time.localtime(r['at']))} for r in rows]})
