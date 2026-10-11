"""Non-blocking access test; never marks a firmware mapping verified."""
from PySide6.QtCore import QObject, Signal, QRunnable, QThreadPool, Qt
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton, QDialogButtonBox
from .snmp_access import diagnose

class ResultSignals(QObject):
    done = Signal(object)

class AccessTask(QRunnable):
    def __init__(self, host, community, source, port):
        super().__init__(); self.args = (host, community, source, port); self.signals = ResultSignals()
    def run(self):
        try:
            results = diagnose(*self.args)
            self.signals.done.emit(results)
        finally:
            self.args = None

class AccessDialog(QDialog):
    def __init__(self, parent, host, community, source='', port=161):
        super().__init__(parent); self.host=host; self.community=community; self.port=port; self.task=None
        self.setWindowTitle('Read-only SNMP access test'); self.resize(600,330)
        layout=QVBoxLayout(self)
        label=QLabel('Tests SNMP v2c and v1 using system description only. This does not verify radio signal metrics, change device settings, or save credentials.'); label.setWordWrap(True); layout.addWidget(label)
        target=QLabel('Management IP: '+host+' · UDP port '+str(port)); target.setTextFormat(Qt.PlainText); layout.addWidget(target)
        layout.addWidget(QLabel('Local source IP (blank uses the Windows route):'))
        self.source=QLineEdit(source); layout.addWidget(self.source)
        self.start=QPushButton('Start access test'); self.start.clicked.connect(self.begin); layout.addWidget(self.start)
        self.result=QLabel('Ready. No test sent.'); self.result.setTextFormat(Qt.PlainText); self.result.setWordWrap(True); layout.addWidget(self.result)
        self.buttons=QDialogButtonBox(QDialogButtonBox.Close); self.buttons.rejected.connect(self.reject); layout.addWidget(self.buttons)
    def begin(self):
        if self.task: return
        self.start.setEnabled(False); self.source.setEnabled(False); self.buttons.setEnabled(False)
        self.result.setText('Checking v2c and v1 in the background… maximum 16 seconds.')
        self.task=AccessTask(self.host,self.community,self.source.text().strip(),self.port)
        self.task.signals.done.connect(self.finished_test)
        QThreadPool.globalInstance().start(self.task)
    def finished_test(self, results):
        self.result.setText('\n\n'.join('SNMP v'+r.version+' · '+r.state+'\n'+r.detail for r in results))
        self.task=None; self.start.setEnabled(True); self.source.setEnabled(True); self.buttons.setEnabled(True)
    def reject(self):
        if self.task: return
        self.community=''; super().reject()
    def closeEvent(self, event):
        if self.task: event.ignore()
        else: self.community=''; super().closeEvent(event)
