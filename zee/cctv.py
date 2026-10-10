"""Camera service health is distinct from ICMP and video playback."""
from dataclasses import replace
from PySide6.QtWidgets import QDialog,QVBoxLayout,QFormLayout,QLineEdit,QSpinBox,QLabel,QPushButton,QDialogButtonBox,QMessageBox,QCheckBox

def camera_health(device,row,now):
    if not device.service_url:return 'Not configured'
    if not row or now-row.get('at',0)>max(30,device.integration.get('poll_seconds',30)*3):return 'Unknown / stale'
    service=row.get('service','Unavailable')
    if 'authentication required' in service.lower():return 'Authentication required — service responds; video untested'
    if 'service responding' in service.lower():return 'Service responding — video untested'
    return 'Service unavailable — '+service

class CameraDialog(QDialog):
    def __init__(self,w,d):
        super().__init__(w);self.w=w;self.d=d;self.setWindowTitle('Camera / NVR service setup');layout=QVBoxLayout(self);form=QFormLayout();layout.addLayout(form)
        self.management=QLineEdit(d.management_url);form.addRow('Management HTTP/HTTPS URL',self.management)
        self.service=QLineEdit(d.service_url);form.addRow('Service HTTP/HTTPS/RTSP URL',self.service)
        self.interval=QSpinBox();self.interval.setRange(5,3600);self.interval.setValue(d.integration.get('poll_seconds',30));form.addRow('Service polling interval (seconds)',self.interval)
        self.alerts=QCheckBox('Alert when saved camera service check fails');self.alerts.setChecked(d.integration.get('service_alerts',False));form.addRow(self.alerts)
        note=QLabel('URLs may include ports, but never username/password. Use Secure settings for protected credentials. Service checks do not prove video is playing. RTSP authentication-required is shown separately. External player login is manual; continuous previews and ONVIF are not included.');note.setWordWrap(True);layout.addWidget(note)
        test=QPushButton('Test saved camera service');test.clicked.connect(self.test);layout.addWidget(test)
        box=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);box.accepted.connect(self.accept);box.rejected.connect(self.reject);layout.addWidget(box)
    def test(self):
        if self.w.measurements.submit(self.d):QMessageBox.information(self,'Service check started','Open Device details for the result. Save changed endpoints before testing.')
        else:QMessageBox.information(self,'Check not started','Enable and configure the device, verify network routing, or wait for running checks.')
    def accept(self):
        try:
            d=replace(self.d,management_url=self.management.text().strip(),service_url=self.service.text().strip(),integration=self.d.integration|{'poll_seconds':self.interval.value(),'service_alerts':self.alerts.isChecked()});d.validate();self.w.store.save(d)
            self.w.measurements.latest.pop(d.id,None);self.w.reload()
        except (ValueError,OSError) as e:QMessageBox.warning(self,'Cannot save camera',str(e));return
        super().accept()
