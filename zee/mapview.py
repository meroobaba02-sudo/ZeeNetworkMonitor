"""Offline schematic map with live markers; never paints invented monitoring data."""
import math
import random
import time
from PySide6.QtCore import Qt,QPointF,QRectF,Signal
from PySide6.QtGui import QColor,QPainter,QPen,QPainterPath,QFont
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QLineEdit,QFrame,QTextEdit,QSplitter,QScrollArea)
from .core import diagnoses

COLORS={'Online':'#28e3a0','Warning':'#ffbd4b','No reply':'#ff6478','Unknown':'#9aacc0','Checking':'#59c9ff','Disabled':'#63768d','Unconfigured':'#9aacc0','Probe error':'#ffbd4b'}
# Layout anchors only. These are neither coordinates nor actual monitored stations.
ANCHORS={'lahore':(.79,.77),'sheikhupura':(.62,.53),'hafizabad':(.46,.29),'sargodha':(.20,.37)}

def auto_position(d,index):
    if d.map_x is not None and d.map_y is not None:return d.map_x,d.map_y
    text=(d.location+' '+d.name).lower()
    for name,pos in ANCHORS.items():
        if name in text:
            import hashlib
            angle=(int(hashlib.sha256(d.id.encode()).hexdigest()[:8],16)%628)/100
            return max(.08,min(.92,pos[0]+.075*math.cos(angle))),max(.1,min(.88,pos[1]+.075*math.sin(angle)))
    return .15+(index%4)*.20,.16+(index//4%4)*.20

class MapCanvas(QWidget):
    selected=Signal(str)
    moved=Signal(str,float,float)
    def __init__(self,window):
        super().__init__()
        self.window=window
        self.setMinimumSize(450,330)
        self.setMouseTracking(True)
        self.devices=[]
        self.boxes={}
        self.selected_id=''
        self.query=''
        self.zoom=1.0
        self.offset=QPointF()
        self.drag_id=''
        self.press=None
        self.did_drag=False
        rng=random.Random(9)
        self.fields=[(rng.random(),rng.random(),rng.uniform(.01,.06),rng.uniform(.015,.08),rng.choice(['#0c2531','#102e36','#142c30','#0b222f'])) for _ in range(460)]
        self.controls=QHBoxLayout()
        outer=QVBoxLayout(self)
        outer.addLayout(self.controls)
        self.controls.addStretch()
        for text,fn in [('+',lambda:self.set_zoom(self.zoom*1.2)),('−',lambda:self.set_zoom(self.zoom/1.2)),('Reset',self.reset)]:
            b=QPushButton(text);b.setFixedHeight(30);b.clicked.connect(fn);self.controls.addWidget(b)
        outer.addStretch()
        label=QLabel('Offline schematic map • drag markers to arrange • wheel to zoom')
        label.setStyleSheet('color:#a2b4c5; background:#091a2b; padding:5px; font-size:11px;')
        outer.addWidget(label)

    def set_zoom(self,value):
        self.zoom=max(.6,min(2.8,value));self.update()

    def reset(self):
        self.zoom=1.;self.offset=QPointF();self.update()

    def point(self,x,y):
        return QPointF((x-.5)*self.width()*self.zoom+self.width()/2+self.offset.x(),(y-.5)*self.height()*self.zoom+self.height()/2+self.offset.y())

    def visible(self,d):
        return not self.query or self.query in (d.name+' '+d.host+' '+d.location+' '+d.notes).casefold()

    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(),QColor('#081c2b'))
        for x,y,w,h,color in self.fields:
            a=self.point(x,y);p.fillRect(QRectF(a.x(),a.y(),w*self.width()*self.zoom,h*self.height()*self.zoom),QColor(color))
        # Faint abstract roads and river: decorative rather than geographic imagery.
        for k in range(12):
            path=QPainterPath(self.point(-.1,k/11))
            path.cubicTo(self.point(.2,k/11+.06),self.point(.65,k/11-.08),self.point(1.1,k/11+.03))
            p.setPen(QPen(QColor('#24404b'),1));p.drawPath(path)
        river=QPainterPath(self.point(.08,-.1))
        river.cubicTo(self.point(.38,.18),self.point(-.05,.38),self.point(.15,.62))
        river.cubicTo(self.point(.30,.75),self.point(.38,.86),self.point(.29,1.1))
        p.setPen(QPen(QColor('#125064'),12*self.zoom));p.drawPath(river)
        for name,(x,y) in ANCHORS.items():
            p.setPen(QColor('#6e8b96'));p.setFont(QFont('Segoe UI',13,QFont.Bold))
            pt=self.point(x,y);p.drawText(QPointF(pt.x()-38,pt.y()+54),name.title())
        points={d.id:self.point(*auto_position(d,i)) for i,d in enumerate(self.devices)}
        states={d.id:self.window.state(d) for d in self.devices}
        for d in self.devices:
            if d.parent not in points:continue
            a,b=points[d.parent],points[d.id]
            state=states[d.id]
            color=COLORS[state] if state in ('Warning','No reply') else ('#28e3a0' if states.get(d.parent) in ('Online','Warning') and state=='Online' else '#607c8c')
            path=QPainterPath(a);path.cubicTo(QPointF(a.x(),(a.y()+b.y())/2),QPointF(b.x(),(a.y()+b.y())/2),b)
            pen=QPen(QColor(color),2.5)
            if state in ('No reply','Warning'):pen.setStyle(Qt.DashLine)
            p.setPen(pen);p.drawPath(path)
        self.boxes={}
        for d in self.devices:
            if not self.visible(d):continue
            pos=points[d.id];state=states[d.id];color=QColor(COLORS[state])
            p.setOpacity(1.0)
            if d.id==self.selected_id:
                p.setPen(QPen(QColor('#31dcdf'),2));p.setBrush(QColor('#143846'));p.drawEllipse(pos,32,32)
            p.setPen(QPen(color,2));p.setBrush(QColor('#082131'))
            p.drawEllipse(pos,23,23)
            self.draw_device(p,d,pos,color)
            box=QRectF(pos.x()-76,pos.y()+27,152,53)
            p.setPen(QPen(QColor('#26455a'),1));p.setBrush(QColor('#081c2f'));p.drawRoundedRect(box,7,7)
            p.setPen(QColor('#ecf3fa'));p.setFont(QFont('Segoe UI',10,QFont.Bold));p.drawText(box.adjusted(9,4,-9,-28),Qt.AlignLeft|Qt.AlignVCenter,p.fontMetrics().elidedText(d.name,Qt.ElideRight,134))
            latest=self.window.latest.get(d.id,{})
            latency=f"{latest['latency']:.1f} ms" if latest.get('latency') is not None and state in ('Online','Warning') else state
            p.setPen(color);p.setFont(QFont('Segoe UI',9));p.drawText(box.adjusted(9,25,-9,-3),Qt.AlignLeft|Qt.AlignVCenter,'●  '+latency)
            self.boxes[d.id]=box.united(QRectF(pos.x()-27,pos.y()-27,54,54))
        if not self.devices:
            p.setPen(QColor('#d7e7ef'));p.setFont(QFont('Segoe UI',14,QFont.Bold))
            p.drawText(self.rect(),Qt.AlignCenter,'Add your first device to see live network status\nUse Add device or Add 5 WAN templates')

    def draw_device(self,p,d,pos,color):
        p.setPen(QPen(color,2))
        x,y=pos.x(),pos.y()
        if 'radio' in d.kind:
            p.drawLine(QPointF(x,y-14),QPointF(x-10,y+14));p.drawLine(QPointF(x,y-14),QPointF(x+10,y+14))
            for h in (-2,6,13):p.drawLine(QPointF(x-7,y+h),QPointF(x+7,y+h))
            p.drawArc(QRectF(x-17,y-21,34,23),20*16,140*16)
        elif 'CCTV' in d.kind:
            p.drawRoundedRect(QRectF(x-12,y-8,19,13),2,2);p.drawLine(QPointF(x-2,y+5),QPointF(x+4,y+14));p.drawRect(QRectF(x+7,y-5,8,7))
        elif 'WAN' in d.kind:
            p.drawEllipse(pos,12,12);p.drawEllipse(QRectF(x-5,y-12,10,24));p.drawLine(QPointF(x-12,y),QPointF(x+12,y))
        else:
            p.drawRoundedRect(QRectF(x-14,y-5,28,17),3,3)
            for xx in (-8,0,8):p.drawPoint(QPointF(x+xx,y+5))
            p.drawLine(QPointF(x-8,y-5),QPointF(x-8,y-15));p.drawLine(QPointF(x+8,y-5),QPointF(x+8,y-15))

    def mousePressEvent(self,event):
        self.press=event.position();self.did_drag=False
        for id,box in reversed(list(self.boxes.items())):
            if box.contains(event.position()):
                self.drag_id=id;self.selected_id=id;self.selected.emit(id);self.update();return
        self.drag_id=''

    def mouseMoveEvent(self,event):
        if not self.press:
            for id,box in self.boxes.items():
                if box.contains(event.position()):
                    d=next(d for d in self.devices if d.id==id);self.setToolTip(d.name+'\n'+(d.host or 'Unconfigured')+'\n'+self.window.state(d));break
            else:self.setToolTip('')
            return
        delta=event.position()-self.press
        if abs(delta.x())+abs(delta.y())<5 and not self.did_drag:return
        self.did_drag=True
        if self.drag_id:
            x=.5+(event.position().x()-self.width()/2-self.offset.x())/(self.width()*self.zoom)
            y=.5+(event.position().y()-self.height()/2-self.offset.y())/(self.height()*self.zoom)
            d=next(d for d in self.devices if d.id==self.drag_id)
            self.preview=(d.id,max(.04,min(.96,x)),max(.06,min(.88,y)))
            # Transient view-only position; probe snapshots remain unchanged.
            from dataclasses import replace
            self.devices=[replace(item,map_x=self.preview[1],map_y=self.preview[2]) if item.id==d.id else item for item in self.devices]
        else:
            self.offset+=delta;self.press=event.position()
        self.update()

    def mouseReleaseEvent(self,event):
        if self.drag_id and self.did_drag and hasattr(self,'preview'):self.moved.emit(*self.preview)
        self.drag_id='';self.press=None

    def wheelEvent(self,event):
        self.set_zoom(self.zoom*(1.12 if event.angleDelta().y()>0 else 1/1.12))

class MapDashboard(QWidget):
    def __init__(self,window):
        super().__init__();self.window=window;self.selected_id=''
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0)
        cards=QHBoxLayout();self.cards=[]
        for label in ('Devices','Online','Warnings','No reply'):
            card=QLabel('0\n'+label);card.setObjectName('mapCard');cards.addWidget(card);self.cards.append(card)
        layout.addLayout(cards)
        tools=QHBoxLayout()
        self.search=QLineEdit();self.search.setPlaceholderText('Search map devices / locations…');self.search.textChanged.connect(self.filter)
        tools.addWidget(self.search)
        for title,fn in [('Add device',window.add),('Add 5 WANs',window.wan_templates)]:
            b=QPushButton(title);b.clicked.connect(fn);tools.addWidget(b)
        layout.addLayout(tools)
        split=QSplitter(Qt.Horizontal)
        self.canvas=MapCanvas(window);self.canvas.selected.connect(self.select);self.canvas.moved.connect(self.move)
        split.addWidget(self.canvas)
        panel=QWidget();panel.setMinimumWidth(260);panel.setMaximumWidth(330);detail=QVBoxLayout(panel)
        self.name=QLabel('Select a device');self.name.setObjectName('detailTitle');self.name.setWordWrap(True);detail.addWidget(self.name)
        self.type=QLabel('Click a marker to view its status');self.type.setWordWrap(True);detail.addWidget(self.type)
        self.status=QLabel('Unknown');self.status.setObjectName('mapCard');detail.addWidget(self.status)
        self.metrics=QLabel('Latency  —\nPacket loss  —');self.metrics.setObjectName('mapCard');detail.addWidget(self.metrics)
        from .gui import LatencyGraph
        self.graph=LatencyGraph();self.graph.setMinimumHeight(150);self.graph.setMaximumHeight(170);detail.addWidget(self.graph)
        row=QHBoxLayout()
        for title,fn in [('Ping',self.ping),('History',self.history),('Edit',self.edit)]:
            b=QPushButton(title);b.clicked.connect(fn);row.addWidget(b)
        detail.addLayout(row)
        self.info=QLabel('No telemetry is shown until a device is configured and measured.');self.info.setWordWrap(True);detail.addWidget(self.info)
        self.wans=QLabel('WAN connections\nNo WAN devices configured');self.wans.setWordWrap(True);self.wans.setObjectName('mapCard');detail.addWidget(self.wans)
        detail.addStretch()
        note=QLabel('No ping reply does not confirm a physical fault.');note.setWordWrap(True);note.setObjectName('subtitle');detail.addWidget(note)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(panel)
        scroll.setMinimumWidth(275);scroll.setMaximumWidth(345)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        split.addWidget(scroll);split.setSizes([900,285]);layout.addWidget(split,1)
        self.events=QLabel('Recent events — no device observations yet');self.events.setObjectName('mapEvents');self.events.setWordWrap(True);layout.addWidget(self.events)

    def filter(self,text):
        self.canvas.query=text.casefold();self.canvas.update()

    def device(self):
        return next((d for d in self.window.devices if d.id==self.selected_id),None)

    def select(self,id):
        self.selected_id=id;self.canvas.selected_id=id;self.refresh()

    def move(self,id,x,y):
        from dataclasses import replace
        d=next((d for d in self.window.devices if d.id==id),None)
        if d:
            self.window.store.save(replace(d,map_x=x,map_y=y));self.window.reload()

    def ping(self):
        d=self.device()
        if d and d.enabled and d.host:self.window.requested.add(d.id);self.window.drain()

    def history(self):
        d=self.device()
        if d:
            self.window.history_device.setCurrentIndex(self.window.history_device.findData(d.id));self.window.tabs.setCurrentIndex(2)

    def edit(self):
        d=self.device()
        if d:self.window.edit_device(d)

    def refresh(self):
        w=self.window;self.canvas.devices=list(w.devices);self.canvas.update()
        states=[w.state(d) for d in w.devices]
        for card,value,label in zip(self.cards,[len(states),states.count('Online'),states.count('Warning'),states.count('No reply')],['Devices','Online','Warnings','No reply']):card.setText(f'{value}    {label}')
        d=self.device()
        if d:
            state=w.state(d);s=w.store.stats(d.id);latest=w.latest.get(d.id,{})
            self.name.setText(d.name);self.type.setText(d.kind+'\n'+d.location);self.status.setText('●  '+state);self.status.setStyleSheet('color:'+COLORS[state])
            latency=f"{latest['latency']:.1f} ms" if latest.get('latency') is not None else '—'
            loss=f"{s['loss']:.1f}%" if s['loss'] is not None else '—'
            self.metrics.setText(f'Latest latency  {latency}\nSample packet loss  {loss}')
            self.graph.rows=w.store.samples(d.id,time.time()-86400)[-1000:];self.graph.update()
            parent=next((a.name for a in w.devices if a.id==d.parent),'None')
            self.info.setText(f'IP / host: {d.host or "Unconfigured"}\nParent: {parent}\nChecks: {s["n"]}\n'+('Suspected fault only — verify route / ICMP policy.' if state=='No reply' else 'Read-only ping observations from this computer.'))
        else:
            self.selected_id='';self.canvas.selected_id='';self.name.setText('Select a device');self.type.setText('Click a marker to view its status');self.status.setText('Unknown');self.metrics.setText('Latency  —\nPacket loss  —');self.graph.rows=[];self.graph.update();self.info.setText('No device selected.')
        wan=[d for d in w.devices if d.wan or d.kind.startswith('WAN')]
        self.wans.setText('WAN connections • reachability only\n'+'\n'.join(d.name+'   '+w.state(d) for d in wan[:8]) if wan else 'WAN connections\nNo WAN devices configured')
        rows=w.store.events(limit=3)
        self.events.setText('RECENT EVENTS\n'+'\n'.join(time.strftime('%H:%M:%S',time.localtime(r['at']))+'   '+r['message'] for r in rows))
