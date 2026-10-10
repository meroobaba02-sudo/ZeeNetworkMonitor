"""Offline schematic map with live markers; never paints invented monitoring data."""
import math
import random
import time
from PySide6.QtCore import Qt,QPointF,QRectF,Signal,QObject,QRunnable,QThreadPool
from PySide6.QtGui import QColor,QPainter,QPen,QPainterPath,QFont
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QLineEdit,QFrame,QTextEdit,QSplitter,QScrollArea,QComboBox,QDialog,QMessageBox,QFileDialog,QInputDialog)
from .customer_theme import status_color
from .core import diagnoses,Device
from . import regionmap
from .towers import TowerDialog
from pathlib import Path
import sys
from dataclasses import replace

COLORS={'Online':'#28e3a0','Warning':'#ffbd4b','No reply':'#ff6478','Unknown':'#9aacc0','Checking':'#59c9ff','Disabled':'#63768d','Unconfigured':'#9aacc0','Probe error':'#ffbd4b'}
def auto_position(d,index):
    if d.map_x is not None and d.map_y is not None:return d.map_x,d.map_y
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
        self.stations=[]
        self.station_boxes={}
        self.dish_boxes={}
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
        for text,fn in [('+',lambda:self.set_zoom(self.zoom*1.2)),('−',lambda:self.set_zoom(self.zoom/1.2)),('Fit',self.fit),('Reset',self.reset)]:
            b=QPushButton(text);b.setFixedHeight(30);b.clicked.connect(fn);self.controls.addWidget(b)
        outer.addStretch()
        self.map_label=QLabel('Zhob–Sambaza • geographic grid • download roads for offline use')
        label=self.map_label
        label.setStyleSheet('color:#a2b4c5; background:#091a2b; padding:5px; font-size:11px;')
        outer.addWidget(label)

    def set_zoom(self,value):
        self.zoom=max(.6,min(2.8,value));self.update()

    def reset(self):
        self.zoom=1.;self.offset=QPointF();self.update()

    def fit(self):
        positions=[auto_position(d,i) for i,d in enumerate(self.devices) if not d.station_id]
        positions += [self.station_position(s,self.window.map_page.map_data['bbox'] if self.window.map_page.map_data else regionmap.BBOX) for s in self.stations]
        if not positions:self.reset();return
        xs,ys=zip(*positions);self.zoom=max(.6,min(2.8,.7/max(.25,max(xs)-min(xs),max(ys)-min(ys))))
        self.offset=QPointF((.5-(min(xs)+max(xs))/2)*self.width()*self.zoom,(.5-(min(ys)+max(ys))/2)*self.height()*self.zoom);self.update()

    def point(self,x,y):
        return QPointF((x-.5)*self.width()*self.zoom+self.width()/2+self.offset.x(),(y-.5)*self.height()*self.zoom+self.height()/2+self.offset.y())

    def visible(self,d):
        return not self.query or self.query in (d.name+' '+d.host+' '+d.location+' '+d.notes).casefold()

    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(),QColor('#081c2b'))
        data=self.window.map_page.map_data
        bbox=data['bbox'] if data else regionmap.BBOX
        self.draw_region(p,data,bbox)
        points={d.id:self.point(*auto_position(d,i)) for i,d in enumerate(self.devices) if not d.station_id}
        station_points={st.id:self.point(*self.station_position(st,bbox)) for st in self.stations}
        for st in self.stations:
            radios=[d for d in self.devices if d.station_id==st.id]
            for side in ('Left','Right'):
                for i,d in enumerate(r for r in radios if r.dish_side==side):
                    center=station_points[st.id]
                    points[d.id]=QPointF(center.x()+(-31 if side=='Left' else 31),center.y()-20+min(i,3)*12)
        states={d.id:self.window.state(d) for d in self.devices}
        for d in self.devices:
            link_id=d.peer_id or d.parent
            if link_id not in points or d.id not in points:continue
            parent=next((a for a in self.devices if a.id==link_id),None)
            if d.peer_id and parent and parent.peer_id==d.id and d.id>parent.id:continue
            if d.station_id and parent and parent.station_id==d.station_id:continue
            a,b=points[link_id],points[d.id]
            state=states[d.id]
            color=COLORS[state] if state in ('Warning','No reply') else ('#28e3a0' if states.get(link_id) in ('Online','Warning') and state=='Online' else '#607c8c')
            path=QPainterPath(a);path.cubicTo(QPointF(a.x(),(a.y()+b.y())/2),QPointF(b.x(),(a.y()+b.y())/2),b)
            if 'radio' in d.kind:color=self.radio_color(d,state).name()
            peer_labels=None
            if 'radio' in d.kind and d.peer_id and parent:
                from .network_paths import peer_quality
                label,peer_labels=peer_quality(d,parent,self.window.measurements.latest,time.time())
                color={'Good':'#28e3a0','Fair':'#ffdd55','Poor':'#ff9933','Critical':'#ff6478','Unknown':'#9aacc0'}[label]
            pen=QPen(QColor(color),2.5)
            if state in ('No reply','Warning') or states.get(link_id) in ('No reply','Warning'):pen.setStyle(Qt.DashLine)
            p.setPen(pen);p.drawPath(path)
            if 'radio' in d.kind:
                r=self.window.measurements.latest.get(d.id,{})
                fresh=time.time()-r.get('at',0)<=max(30,d.integration.get('poll_seconds',30)*3)
                m=r.get('metrics',{}) if fresh else {}
                text=f"{m.get('signal_dbm','—')} dBm • CCQ {m.get('tx_ccq','—')}% • TX/RX {m.get('tx_mbps','—')}/{m.get('rx_mbps','—')} Mbps"
                if peer_labels:text='Endpoints: '+ ' / '.join(peer_labels)+' • '+text
                p.setFont(QFont('Segoe UI',8));p.setPen(QColor('#acc7dd'));p.drawText((a+b)/2,text)
        self.boxes={};self.station_boxes={};self.dish_boxes={}
        for st in self.stations:
            radios=[d for d in self.devices if d.station_id==st.id]
            if self.query and self.query not in st.name.casefold() and not any(self.visible(d) for d in radios):continue
            pos=station_points[st.id];x,y=pos.x(),pos.y()
            p.setPen(QPen(QColor('#8fc8dc'),3));p.setBrush(Qt.NoBrush)
            p.drawLine(QPointF(x,y-45),QPointF(x-20,y+32));p.drawLine(QPointF(x,y-45),QPointF(x+20,y+32))
            for k in range(4):
                h=-25+k*18;half=(h+45)*20/77
                p.drawLine(QPointF(x-half,y+h),QPointF(x+half,y+h))
                p.drawLine(QPointF(x-half,y+h),QPointF(x+(h+63)*20/77,y+h+18))
            for d in radios[:8]:
                dp=points[d.id];color=self.radio_color(d,states[d.id])
                p.setPen(QPen(color,2));p.setBrush(QColor('#092a38'));p.drawLine(QPointF(x,dp.y()),dp);p.drawEllipse(dp,10,8)
                if self.selected_id==d.id:p.drawEllipse(dp,14,12)
                self.dish_boxes[d.id]=QRectF(dp.x()-14,dp.y()-12,28,24)
            online=sum(states[d.id]=='Online' for d in radios)
            fault=any(states[d.id]=='No reply' for d in radios)
            color=QColor('#ff6478' if fault else '#28e3a0' if radios and online==len(radios) else '#9aacc0')
            box=QRectF(x-90,y+35,180,54)
            p.setPen(QPen(color,2 if self.selected_id==st.id else 1));p.setBrush(QColor('#081c2f'));p.drawRoundedRect(box,7,7)
            p.setFont(QFont('Segoe UI',10,QFont.Bold));p.setPen(QColor('#ecf3fa'));p.drawText(box.adjusted(8,3,-8,-26),Qt.AlignCenter,p.fontMetrics().elidedText(st.name,Qt.ElideRight,164))
            p.setFont(QFont('Segoe UI',9));p.setPen(color);p.drawText(box.adjusted(8,27,-8,-3),Qt.AlignCenter,f'{online}/{len(radios)} Online' if radios else 'No radios • Add radio')
            self.station_boxes[st.id]=box.united(QRectF(x-46,y-49,92,85))
        for d in self.devices:
            if d.station_id or not self.visible(d):continue
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
        if not self.devices and not self.stations:
            p.setPen(QColor('#d7e7ef'));p.setFont(QFont('Segoe UI',14,QFont.Bold))
            p.drawText(self.rect(),Qt.AlignCenter,'Add a tower, then attach its radios\nExisting devices: Edit → Physical tower')

    def radio_color(self,d,ping_state):
        from .telemetry import quality
        result=self.window.measurements.latest.get(d.id,{})
        score,label=quality(result.get('metrics',{}),d.integration,time.time()-result.get('at',0))
        return QColor({'Good':'#28e3a0','Fair':'#ffdd55','Poor':'#ff9933','Critical':'#ff6478','Unknown':'#9aacc0'}[label])

    def mouseDoubleClickEvent(self,event):
        for id,box in {**self.boxes,**self.dish_boxes}.items():
            if box.contains(event.position()):
                d=next((d for d in self.devices if d.id==id),None)
                if d:self.window.show_details(d);self.window.open_management(d)
                return

    def station_position(self,st,bbox):
        if st.latitude is not None:return regionmap.position(st.latitude,st.longitude,bbox)
        return st.map_x,st.map_y

    def draw_region(self,p,data,bbox):
        p.setPen(QPen(QColor('#163744'),1))
        for k in range(11):
            p.drawLine(self.point(k/10,0),self.point(k/10,1));p.drawLine(self.point(0,k/10),self.point(1,k/10))
        if data:
            for f in data['features']:
                if f['kind']=='place' or not f['points']:continue
                path=QPainterPath(self.point(*regionmap.position(*f['points'][0],bbox)))
                for lat,lon in f['points'][1:]:path.lineTo(self.point(*regionmap.position(lat,lon,bbox)))
                road=f['kind']=='road'
                major=f.get('class') in ('trunk','primary','secondary')
                p.setPen(QPen(QColor('#597275' if road else '#17667e'),2.2 if major else 1.0));p.setBrush(Qt.NoBrush);p.drawPath(path)
            p.setFont(QFont('Segoe UI',8));p.setPen(QColor('#90adb9'))
            for f in data['features']:
                if f['kind']=='place' and f['points'] and f['name']:
                    pt=self.point(*regionmap.position(*f['points'][0],bbox));p.drawText(pt,f['name'][:45])
        p.setFont(QFont('Segoe UI',11,QFont.Bold));p.setPen(QColor('#e2d6a0'))
        for name,lat,lon in [('Zhob',31.34082,69.4493),('Sambaza Fort',31.773901,69.349685)]:
            x,y=regionmap.position(lat,lon,bbox)
            if 0<=x<=1 and 0<=y<=1:
                pt=self.point(x,y);p.drawEllipse(pt,3,3);p.drawText(pt+QPointF(7,-7),name)

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
        for id,box in reversed(list(self.dish_boxes.items())):
            if box.contains(event.position()):
                self.drag_id='';self.selected_id=id;self.selected.emit(id);self.update();return
        for id,box in reversed(list(self.boxes.items())+list(self.station_boxes.items())):
            if box.contains(event.position()):
                self.drag_id=id;self.selected_id=id;self.selected.emit(id);self.update();return
        self.drag_id=''

    def mouseMoveEvent(self,event):
        if not self.press:
            for id,box in {**self.boxes,**self.dish_boxes}.items():
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
            st=next((st for st in self.stations if st.id==self.drag_id),None)
            if st:
                self.preview=(st.id,max(.04,min(.96,x)),max(.06,min(.88,y)))
                self.stations=[replace(item,map_x=self.preview[1],map_y=self.preview[2],latitude=None,longitude=None) if item.id==st.id else item for item in self.stations]
                self.update();return
            d=next(d for d in self.devices if d.id==self.drag_id)
            self.preview=(d.id,max(.04,min(.96,x)),max(.06,min(.88,y)))
            # Transient view-only position; probe snapshots remain unchanged.
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
        super().__init__();self.window=window;self.selected_id='';self.station_id=''
        self.map_data=None;self.map_error='';self.closing=False;self.last_download=0
        self.map_path=window.store.path.parent/'region_map.json'
        bundled=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[1]))/'assets/region_map.json.gz'
        try:
            self.map_data=regionmap.load(self.map_path if self.map_path.exists() else bundled)
        except (ValueError,OSError,KeyError):pass
        self.map_pool=QThreadPool();self.map_pool.setMaxThreadCount(1)
        self.map_signals=MapSignals();self.map_signals.done.connect(self.map_finished)
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0)
        cards=QHBoxLayout();self.cards=[]
        for label in ('Devices','Online','Warnings','No reply'):
            card=QLabel('0\n'+label);card.setObjectName('mapCard');cards.addWidget(card);self.cards.append(card)
        layout.addLayout(cards)
        tools=QHBoxLayout()
        self.search=QLineEdit();self.search.setPlaceholderText('Search map devices / locations…');self.search.textChanged.connect(self.filter)
        tools.addWidget(self.search)
        for title,fn in [('Add tower',self.add_tower),('Add device',window.add),('Map options',self.map_options)]:
            b=QPushButton(title);b.clicked.connect(fn);tools.addWidget(b)
        layout.addLayout(tools)
        split=QSplitter(Qt.Horizontal)
        self.canvas=MapCanvas(window);self.canvas.selected.connect(self.select);self.canvas.moved.connect(self.move)
        split.addWidget(self.canvas)
        panel=QWidget();panel.setMinimumWidth(260);panel.setMaximumWidth(330);detail=QVBoxLayout(panel)
        self.tower_name=QLabel('');self.tower_name.setWordWrap(True);detail.addWidget(self.tower_name)
        self.radios=QComboBox();self.radios.currentIndexChanged.connect(self.choose_radio);detail.addWidget(self.radios)
        row=QHBoxLayout()
        for title,fn in [('Add radio',self.add_radio),('Tower',self.edit_tower)]:
            b=QPushButton(title);b.clicked.connect(fn);row.addWidget(b)
        detail.addLayout(row)
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

    def choose_radio(self,index):
        id=self.radios.itemData(index)
        if id:self.select(id)

    def add_tower(self):
        self.tower_dialog(None)

    def edit_tower(self):
        st=next((st for st in self.window.page_stations() if st.id==self.station_id),None)
        if st:self.tower_dialog(st)
        else:QMessageBox.information(self,'Select tower','Click a physical tower first.')

    def tower_dialog(self,st):
        if st is None:
            from .core import Station
            n=len(self.window.page_stations());st=Station(page_id=self.window.page_id,map_x=.5+.35*math.cos(n*2.399963),map_y=.5+.32*math.sin(n*2.399963))
        dialog=TowerDialog(self,st,self.map_data['bbox'] if self.map_data else regionmap.BBOX)
        if dialog.exec()==QDialog.Accepted:
            value=dialog.station();self.window.store.save_station(value);self.window.reload();self.select(value.id)

    def add_radio(self):
        if not self.station_id:
            QMessageBox.information(self,'Select tower','Add or select a physical tower first.');return
        from .gui import DeviceDialog
        d=Device(page_id=self.window.page_id,kind='Rocket M5 / wireless radio',station_id=self.station_id,dish_side='Left' if sum(a.station_id==self.station_id for a in self.window.devices)%2==0 else 'Right')
        dialog=DeviceDialog(self.window.devices,d,self,stations=self.window.page_stations())
        if dialog.exec()==QDialog.Accepted:
            try:
                d=dialog.device();self.window.store.save(d);self.window.reload();self.select(d.id)
            except ValueError as e:QMessageBox.warning(self,'Could not save radio',str(e))

    def map_options(self):
        actions=['Download Zhob–Sambaza roads','Import saved map JSON','Export current map JSON','Set Overpass endpoint','Remove selected tower','Automatic tower layout']
        action,ok=QInputDialog.getItem(self,'Map options','Action',actions,0,False)
        if not ok:return
        if action==actions[0]:self.download_map()
        elif action==actions[1]:
            path,_=QFileDialog.getOpenFileName(self,'Import saved map','','Zee vector map (*.json)')
            if path:
                try:
                    data=regionmap.load(path);regionmap.save(self.map_path,data);self.map_data=data;self.canvas.reset();self.refresh()
                except (ValueError,OSError,TypeError,KeyError) as e:QMessageBox.warning(self,'Invalid map',str(e))
        elif action==actions[2]:
            if not self.map_data:QMessageBox.information(self,'No map','Download a map first.');return
            path,_=QFileDialog.getSaveFileName(self,'Export map','Zhob-Sambaza-map.json','JSON (*.json)')
            if path:
                try:regionmap.save(path,self.map_data)
                except OSError as e:QMessageBox.warning(self,'Export failed',str(e))
        elif action==actions[3]:
            endpoint,ok=QInputDialog.getText(self,'Overpass endpoint','HTTPS interpreter URL (for your own/provider server)',text=self.window.store.setting('map_endpoint',regionmap.ENDPOINT))
            if ok:
                import urllib.parse
                url=urllib.parse.urlparse(endpoint)
                if url.scheme!='https' or not url.hostname:QMessageBox.warning(self,'Invalid URL','Use an HTTPS interpreter URL.');return
                self.window.store.set_setting('map_endpoint',endpoint)
        elif action==actions[5]:
            for i,st in enumerate(self.window.page_stations()):self.window.store.save_station(replace(st,map_x=.15+(i%4)*.22,map_y=.18+(i//4%4)*.20,latitude=None,longitude=None))
            self.window.reload()
        elif self.station_id:
            if QMessageBox.question(self,'Remove tower','Remove tower? Radios and history will remain as standalone devices.')==QMessageBox.Yes:
                self.window.store.delete_station(self.station_id);self.station_id='';self.window.reload();self.refresh()

    def download_map(self):
        if self.map_pool.activeThreadCount() or time.monotonic()-self.last_download<60:
            QMessageBox.information(self,'Map download','A download is running, or please wait a minute before retrying.');return
        self.last_download=time.monotonic()
        self.events.setText('Downloading Zhob–Sambaza roads… Monitoring continues. Existing map stays available.')
        self.map_pool.start(MapDownload(self.map_signals,self.window.store.setting('map_endpoint',regionmap.ENDPOINT)))

    def map_finished(self,data,error):
        if self.closing:return
        if error:QMessageBox.warning(self,'Map download failed',error+'\nExisting map is unchanged. Retry later or import a saved map JSON.');return
        try:regionmap.save(self.map_path,data)
        except OSError as e:QMessageBox.warning(self,'Could not save map',str(e));return
        self.map_data=data;self.canvas.reset();self.refresh()
        QMessageBox.information(self,'Offline map ready','Roads and places saved. This map now works without Internet.')

    def shutdown(self):
        self.closing=True;self.map_pool.waitForDone()

    def filter(self,text):
        self.canvas.query=text.casefold();self.canvas.update()

    def device(self):
        return next((d for d in self.window.devices if d.id==self.selected_id),None)

    def select(self,id):
        station=next((st for st in self.window.page_stations() if st.id==id),None)
        if station:
            self.station_id=id
            self.selected_id=next((d.id for d in self.window.devices if d.station_id==id),'')
        else:
            self.selected_id=id
            d=self.device();self.station_id=d.station_id if d else ''
        self.canvas.selected_id=self.selected_id or self.station_id;self.refresh()

    def move(self,id,x,y):
        st=next((st for st in self.window.page_stations() if st.id==id),None)
        if st:
            lat,lon=regionmap.coordinates(x,y,self.map_data['bbox'] if self.map_data else regionmap.BBOX)
            self.window.store.save_station(replace(st,map_x=x,map_y=y,latitude=lat,longitude=lon));self.window.reload();return
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
        w=self.window;self.canvas.devices=list(w.devices);self.canvas.stations=w.page_stations();self.canvas.update()
        self.canvas.map_label.setText(('Zhob–Sambaza • offline roads map • '+regionmap.ATTRIBUTION) if self.map_data else 'Zhob–Sambaza • GPS grid only • Map options → Download roads')
        st=next((st for st in self.canvas.stations if st.id==self.station_id),None)
        self.radios.blockSignals(True);self.radios.clear()
        if st:
            radios=[d for d in w.devices if d.station_id==st.id]
            self.tower_name.setText(st.name+f' • {sum(w.state(d)=="Online" for d in radios)}/{len(radios)} Online')
            for d in radios:self.radios.addItem(f'{d.name} • {d.dish_side} • {w.state(d)}',d.id)
            self.radios.setCurrentIndex(max(0,self.radios.findData(self.selected_id)))
        else:self.tower_name.setText('Select a tower to manage its radios')
        self.radios.setVisible(bool(st));self.radios.blockSignals(False)
        states=[w.state(d) for d in w.devices]
        for card,value,label in zip(self.cards,[len(states),states.count('Online'),states.count('Warning'),states.count('No reply')],['Devices','Online','Warnings','No reply']):card.setText(f'{value}    {label}')
        d=self.device()
        if d:
            state=w.state(d);s=w.store.stats(d.id);latest=w.latest.get(d.id,{})
            self.name.setText(d.name);self.type.setText(d.kind+'\n'+d.location);self.status.setText('●  '+state);self.status.setStyleSheet('color:'+status_color(state,w.ui_theme))
            latency=f"{latest['latency']:.1f} ms" if latest.get('latency') is not None else '—'
            loss=f"{s['loss']:.1f}%" if s['loss'] is not None else '—'
            self.metrics.setText(f'Latest latency  {latency}\nSample packet loss  {loss}')
            self.graph.rows=w.store.samples(d.id,time.time()-86400)[-1000:];self.graph.update()
            parent=next((a.name for a in w.devices if a.id==d.parent),'None')
            self.info.setText(f'IP / host: {d.host or "Unconfigured"}\nParent: {parent}\nChecks: {s["n"]}\n'+('Suspected fault only — verify route / ICMP policy.' if state=='No reply' else 'Read-only ping observations from this computer.'))
        else:
            self.selected_id='';self.canvas.selected_id=self.station_id;self.name.setText('Select a device');self.type.setText('Click a marker to view its status');self.status.setText('Unknown');self.metrics.setText('Latency  —\nPacket loss  —');self.graph.rows=[];self.graph.update();self.info.setText('No device selected.')
        wan=[d for d in w.devices if d.wan or d.kind.startswith('WAN')]
        self.wans.setText('WAN connections • reachability only\n'+'\n'.join(d.name+'   '+w.state(d) for d in wan[:8]) if wan else 'WAN connections\nNo WAN devices configured')
        ids={d.id for d in w.devices}|{st.id for st in w.page_stations()}
        rows=[r for r in w.store.events(limit=100) if r['device'] in ids][:3]
        self.events.setText('RECENT EVENTS\n'+'\n'.join(time.strftime('%H:%M:%S',time.localtime(r['at']))+'   '+r['message'] for r in rows))


class MapSignals(QObject):
    done=Signal(object,str)

class MapDownload(QRunnable):
    def __init__(self,signals,endpoint):
        super().__init__();self.signals=signals;self.endpoint=endpoint
    def run(self):
        try:self.signals.done.emit(regionmap.download(endpoint=self.endpoint),'')
        except Exception as e:self.signals.done.emit(None,str(e))
