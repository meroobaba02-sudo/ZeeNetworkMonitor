"""Qt-native NOC cards and bounded, timestamp-aware measurement plots."""
import math,time
from PySide6.QtCore import Qt,QPointF,QRectF
from PySide6.QtGui import QPainter,QColor,QPen,QPainterPath
from PySide6.QtWidgets import QLabel,QFrame,QVBoxLayout,QPushButton,QWidget,QApplication
from .customer_theme import THEMES

def text(value='',name=''):
    label=QLabel(value);label.setTextFormat(Qt.PlainText);label.setWordWrap(True)
    if name:label.setObjectName(name)
    return label

def action(title,callback):
    button=QPushButton(title);button.clicked.connect(callback);button.setAccessibleName(title);return button

def number(value):return type(value) in (int,float) and math.isfinite(value)

def current(row,d,now=None):
    age=(time.time() if now is None else now)-row.get('at',0)
    return bool(row) and 0<=age<=max(30,d.integration.get('poll_seconds',30)*3)

class Trend(QWidget):
    def __init__(self,title='Measured history',unit='',parent=None):
        super().__init__(parent);self.title=title;self.unit=unit;self.series=[];self.setMinimumHeight(120);self.setMinimumWidth(180)
    def set_series(self,series):
        self.series=[(name,[(t,v if number(v) else None) for t,v in rows[-240:]],color) for name,rows,color in series];self.update()
    def paintEvent(self,event):
        c=THEMES.get(QApplication.instance().property('zee_theme'),THEMES['dark']);p=QPainter(self);p.setRenderHint(QPainter.Antialiasing);p.fillRect(self.rect(),QColor(c['panel']))
        p.setPen(QColor(c['muted']));p.drawText(10,18,self.title+' · '+self.unit)
        vals=[v for _,rows,_ in self.series for _,v in rows if v is not None];times=[t for _,rows,_ in self.series for t,_ in rows]
        if not vals:p.drawText(self.rect(),Qt.AlignCenter,'No measured history');return
        low,high=min(vals),max(vals);padding=max(1,(high-low)*.1);low-=padding;high+=padding;left,right=min(times),max(times);span=max(1,right-left)
        rect=QRectF(40,30,max(1,self.width()-55),max(1,self.height()-60))
        p.setPen(QPen(QColor(c['line']),1))
        for f in (0,.5,1):
            y=rect.bottom()-rect.height()*f;p.drawLine(QPointF(rect.left(),y),QPointF(rect.right(),y));p.drawText(2,int(y),f'{low+(high-low)*f:.0f}')
        for name,rows,color in self.series:
            path=QPainterPath();previous=False
            for t,v in rows:
                if v is None:previous=False;continue
                point=QPointF(rect.left()+(t-left)/span*rect.width(),rect.bottom()-(v-low)/(high-low)*rect.height())
                if previous:path.lineTo(point)
                else:path.moveTo(point)
                previous=True;p.setPen(QColor(color));p.drawEllipse(point,2,2)
            p.setPen(QPen(QColor(color),2));p.drawPath(path)
        p.setPen(QColor(c['muted']));p.drawText(int(rect.left()),self.height()-7,time.strftime('%H:%M',time.localtime(left)));p.drawText(max(40,self.width()-55),self.height()-7,time.strftime('%H:%M',time.localtime(right)))
        p.drawText(10,30,' / '.join(name for name,_,_ in self.series))

class MetricCard(QFrame):
    def __init__(self,title):
        super().__init__();self.setObjectName('metricCard');layout=QVBoxLayout(self);layout.setContentsMargins(16,13,16,13);layout.addWidget(text(title,'muted'));self.value=text('—','metricValue');layout.addWidget(self.value);self.note=text('No measurements','muted');layout.addWidget(self.note)

def icon(name):
    """Small consistent vector icons; no extra font or image dependency."""
    from PySide6.QtGui import QPixmap,QIcon
    pix=QPixmap(24,24);pix.fill(Qt.transparent);p=QPainter(pix);p.setRenderHint(QPainter.Antialiasing);p.setPen(QPen(QColor('#409ed0'),1.8,Qt.SolidLine,Qt.RoundCap,Qt.RoundJoin));p.setBrush(Qt.NoBrush)
    if 'Dashboard' in name:
        for x,y in [(3,3),(14,3),(3,14),(14,14)]:p.drawRoundedRect(QRectF(x,y,7,7),1,1)
    elif 'Discovery' in name:
        p.drawEllipse(QRectF(3,3,13,13));p.drawLine(15,15,22,22)
    elif 'Internet' in name:
        p.drawEllipse(QRectF(2,2,20,20));p.drawEllipse(QRectF(7,2,10,20));p.drawLine(2,12,22,12)
    elif 'Map' in name or 'Diagnosis' in name:
        p.drawLine(5,5,19,5);p.drawLine(5,5,12,19);p.drawLine(19,5,12,19)
        for x,y in [(5,5),(19,5),(12,19)]:p.setBrush(QColor('#409ed0'));p.drawEllipse(QPointF(x,y),3,3)
    elif 'Alignment' in name:
        p.drawEllipse(QRectF(6,6,12,12));p.drawLine(12,1,12,8);p.drawLine(12,16,12,23);p.drawLine(1,12,8,12);p.drawLine(16,12,23,12)
    elif 'Alerts' in name:
        path=QPainterPath(QPointF(12,3));path.lineTo(22,21);path.lineTo(2,21);path.closeSubpath();p.drawPath(path);p.drawLine(12,8,12,14);p.drawPoint(12,18)
    elif 'Settings' in name or 'Tools' in name:
        p.drawEllipse(QRectF(5,5,14,14));p.drawEllipse(QRectF(9,9,6,6))
        for x,y,x2,y2 in [(12,1,12,5),(12,19,12,23),(1,12,5,12),(19,12,23,12)]:p.drawLine(x,y,x2,y2)
    elif 'Rocket' in name:
        p.drawLine(12,7,4,22);p.drawLine(12,7,20,22);p.drawLine(7,17,17,17);p.drawEllipse(QRectF(9,3,6,6));p.drawArc(QRectF(4,0,16,15),0,180*16)
    else:
        for y in (3,10,17):p.drawRoundedRect(QRectF(3,y,18,5),1,1);p.drawPoint(6,y+2)
    p.end();return QIcon(pix)

def prepare_backup(store,version):
    """One-time SQLite snapshot before first NOC startup; no schema migration."""
    from pathlib import Path
    if store.setting('noc_ui_version')==version:return None
    folder=store.path.parent/'backups';folder.mkdir(exist_ok=True);target=folder/('before-noc-'+version+'.sqlite3');temporary=target.with_suffix('.new.sqlite3')
    if not target.exists():
        try:store.backup(temporary);temporary.replace(target)
        finally:temporary.unlink(missing_ok=True)
    store.set_setting('noc_ui_version',version);return target
