"""Small advanced dialog; daily controls remain in the existing interface."""
from PySide6.QtWidgets import QDialog,QFormLayout,QSpinBox,QCheckBox,QDialogButtonBox,QLabel


class PerformanceDialog(QDialog):
    def __init__(self,window):
        super().__init__(window);self.w=window;self.setWindowTitle('Advanced monitoring / history');form=QFormLayout(self)
        self.fields={}
        for key,label,low,high,default in [
            ('ping_workers','Parallel ping checks',1,16,8),
            ('telemetry_workers','Parallel service checks',1,4,2),
            ('ping_retries','Extra ping retries',0,3,0),
            ('retry_delay','Retry delay (seconds)',1,10,1),
            ('minimum_interval','Minimum ping interval (seconds)',1,3600,1),
            ('refresh_seconds','Screen refresh (seconds)',1,30,2),
            ('incident_days','Alert history (days; 0 = keep)',0,3650,90),
            ('disk_warning_mb','Database disk warning (MB; 0 = off)',0,100000,250)]:
            field=QSpinBox();field.setRange(low,high);field.setValue(window.store.setting(key,default));self.fields[key]=field;form.addRow(label,field)
        self.pause=QCheckBox('Pause periodic monitoring while minimized');self.pause.setChecked(window.store.setting('pause_minimized',False));form.addRow(self.pause)
        self.archive=QCheckBox('Save a database archive before cleanup (uses extra disk)');self.archive.setChecked(window.store.setting('archive_cleanup',False));form.addRow(self.archive)
        text=QLabel('Active alerts, pinned events and security/audit records are protected. Disk threshold warns; cleanup deletes only expired records. Archives are kept until you remove them. Existing per-device intervals stay in effect above the minimum. A running network call finishes within its existing timeout.');text.setWordWrap(True);form.addRow(text)
        buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);form.addRow(buttons)
    def accept(self):
        for key,field in self.fields.items():self.w.store.set_setting(key,field.value())
        self.w.store.set_setting('pause_minimized',self.pause.isChecked());self.w.store.set_setting('archive_cleanup',self.archive.isChecked())
        self.w.apply_performance();super().accept()
