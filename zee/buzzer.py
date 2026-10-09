"""Non-blocking audible alarms; acknowledgment applies only to current incidents."""
from pathlib import Path
import sys
from PySide6.QtCore import QObject,QTimer,Signal
from PySide6.QtWidgets import QApplication

class Buzzer(QObject):
    changed=Signal()
    def __init__(self,parent=None,enabled=True,sound_fn=None):
        super().__init__(parent)
        self.enabled=enabled
        self.active={}
        self.acknowledged={}
        self.playing=False
        self.sound_fn=sound_fn or self.sound
        self.timer=QTimer(self)
        self.timer.setInterval(1600)
        self.timer.timeout.connect(lambda:self.sound_fn(True))

    def sound(self,start):
        if sys.platform=='win32':
            import winsound
            path=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[1]))/'assets/alarm.wav'
            if start:
                winsound.PlaySound(str(path),winsound.SND_FILENAME|winsound.SND_ASYNC|winsound.SND_LOOP|winsound.SND_NODEFAULT)
            else:
                winsound.PlaySound(None,0)
        elif start:
            QApplication.beep()

    def update(self,active):
        self.active=dict(active)
        self.acknowledged={k:v for k,v in self.acknowledged.items() if self.active.get(k)==v}
        self.refresh()

    def set_enabled(self,value):
        self.enabled=bool(value)
        self.refresh()

    def silence(self):
        self.acknowledged=dict(self.active)
        self.refresh()

    def refresh(self):
        should_play=self.enabled and any(self.acknowledged.get(k)!=v for k,v in self.active.items())
        if should_play!=self.playing:
            self.playing=should_play
            try:
                self.sound_fn(should_play)
            except (RuntimeError,OSError):
                if should_play: QApplication.beep()
            if should_play and sys.platform!='win32':self.timer.start()
            else:self.timer.stop()
        self.changed.emit()

    def shutdown(self):
        self.active={}
        self.acknowledged={}
        self.refresh()
        self.timer.stop()
