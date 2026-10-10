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
        self.engine.invalidate();self.measurements.stop();self.requested.clear();self.buzzer.update({});self.page_id=id;self.states.clear();self.latest.clear();self.streaks.clear();self.alerted.clear()
        self.measurements.latest.clear();self.measurements.speed_latest.clear();self.telemetry_alerted.clear()
        self.start_button.setText('▶ Start monitoring');self.store.set_setting('active_page',id);self.reload()
    def scoped_probe(self,d):
        page=self.page_snapshot
        if (page.interface_hint or page.gateway_hint) and not page.routing_verified:return Result(False,error='Network routing not verified; checks paused.',infrastructure_error=True)
        source=d.source or page.source_ip
        try:
            if source:
                if ipaddress.ip_address(source).version!=ipaddress.ip_address(d.host).version:raise ValueError()
            return probe(replace(d,source=source))
        except ValueError:return Result(False,error='Source-bound checks need matching literal IP addresses.',infrastructure_error=True)
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
            self.engine.invalidate();self.measurements.stop();self.requested.clear();self.start_button.setText('▶ Start monitoring');self.reload()
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
            c=sqlite3.connect('file:'+Path(path).as_posix()+'?mode=ro',uri=True)
            try:
                if c.execute('PRAGMA integrity_check').fetchone()[0]!='ok' or c.execute('PRAGMA user_version').fetchone()[0] not in (1,2,3):raise ValueError('Invalid or unsupported backup.')
                c.execute('SELECT data FROM devices LIMIT 1')
            finally:c.close()
            if QMessageBox.question(self,'Restore and restart','Replace current configuration/history on next launch? A safety backup will be kept. Credentials remain on this Windows account.')!=QMessageBox.Yes:return
            import shutil
            shutil.copyfile(path,self.store.path.parent/'restore.pending.sqlite3');self.close()
        except (OSError,ValueError,sqlite3.Error) as e:QMessageBox.warning(self,'Restore failed',str(e))
    def license_dialog(self):
        from .system_dialogs import LicenseDialog
        LicenseDialog(self).exec()
    def mobile_dialog(self):
        from .system_dialogs import MobileDialog
        MobileDialog(self).exec()
    def update_mobile(self):
        server=getattr(self,'mobile_server',None)
        if not server:return
        import time
        from .telemetry import quality
        pages=self.store.pages();names={p.id:p.name for p in pages};towers={s.id:s.name for s in self.store.stations()};devices=[]
        for d in self.store.devices():
            r=self.measurements.latest.get(d.id,{}) if d.page_id==self.page_id else {};age=time.time()-r.get('at',0);fresh=age<=max(30,d.integration.get('poll_seconds',30)*3)
            devices.append({'name':d.name,'page':d.page_id,'network':names.get(d.page_id,''),'tower':towers.get(d.station_id,''),'status':self.state(d) if d.page_id==self.page_id else 'Not monitored','quality':quality(r.get('metrics',{}),d.integration,age)[1],'internet':r.get('internet','Unknown') if fresh else 'Unknown','download':str(round(r['download_mbps'],2))+' Mbps (traffic)' if fresh and 'download_mbps' in r else 'Unavailable','upload':str(round(r['upload_mbps'],2))+' Mbps (traffic)' if fresh and 'upload_mbps' in r else 'Unavailable'})
        server.update({'at':time.time(),'pages':[{'id':p.id,'name':p.name} for p in pages if not p.archived],'devices':devices,'events':[r['message'] for r in self.store.events(limit=20) if r['kind']=='alert']})
