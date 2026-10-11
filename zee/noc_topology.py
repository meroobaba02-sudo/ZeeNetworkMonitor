"""Interactive schematic topology from saved stations and explicit parent/peer links."""
from PySide6.QtCore import Qt,QRectF
from PySide6.QtGui import QPen,QColor,QBrush,QPainter
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QGraphicsView,QGraphicsScene,QGraphicsRectItem,QGraphicsSimpleTextItem,QApplication,QLineEdit
from .noc_widgets import action,text
from .customer_theme import THEMES,status_color

class Node(QGraphicsRectItem):
    def __init__(self,rect,callback):super().__init__(rect);self.callback=callback;self.setFlag(QGraphicsRectItem.ItemIsSelectable,True)
    def mouseReleaseEvent(self,event):
        super().mouseReleaseEvent(event)
        if event.button()==Qt.LeftButton:self.callback()

class View(QGraphicsView):
    def wheelEvent(self,event):
        if event.angleDelta().y():self.scale_by(1.15 if event.angleDelta().y()>0 else 1/1.15)
        event.accept()
    def scale_by(self,value):
        scale=self.transform().m11()*value
        if .15<=scale<=4:self.scale(value,value)

class TopologyPanel(QWidget):
    def __init__(self,w):
        super().__init__();self.w=w;self.key=None;self.query='';layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0);self.caption=text('Configured topology','sectionTitle');layout.addWidget(self.caption);layout.addWidget(text('Schematic · stations and configured parent/peer links only. Green = reply, yellow = warning, red = no reply / critical measured radio quality; a red line does not confirm a physical break. Click nodes for details; drag blank space to pan.','muted'))
        tools=QHBoxLayout();layout.addLayout(tools);self.route=QLineEdit(w.store.setting('topology_route_title','Lahore — intermediate stations — Sargodha'));self.route.setToolTip('Operator reference label only; does not create stations or connectivity.');self.route.editingFinished.connect(lambda:w.store.set_setting('topology_route_title',self.route.text()[:200]));tools.addWidget(self.route,1)
        self.scene=QGraphicsScene(self);self.view=View(self.scene);self.view.setRenderHint(QPainter.Antialiasing);self.view.setDragMode(QGraphicsView.ScrollHandDrag);self.view.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        for title,fn in [('+',lambda:self.view.scale_by(1.2)),('−',lambda:self.view.scale_by(1/1.2)),('Fit',self.fit)]:tools.addWidget(action(title,fn))
        layout.addWidget(self.view,1);self.evidence=text('No configured links','muted');layout.addWidget(self.evidence)
    def open_device(self,d):self.w.map_page.select(d.id);self.w.show_details(d)
    def fit(self):
        if self.scene.items():self.view.fitInView(self.scene.itemsBoundingRect().adjusted(-25,-25,25,25),Qt.KeepAspectRatio)
    def refresh(self):
        devices=self.w.devices;stations=self.w.page_stations();states={d.id:self.w.state(d) for d in devices};theme=self.w.ui_theme
        from .telemetry import quality
        import time
        health={d.id:quality(self.w.measurements.latest.get(d.id,{}).get('metrics',{}),d.integration,time.time()-self.w.measurements.latest.get(d.id,{}).get('at',0))[1] for d in devices}
        key=(theme,self.query,tuple((d.id,d.name,d.host,d.station_id,d.parent,d.peer_id,states[d.id],health[d.id]) for d in devices),tuple((s.id,s.name) for s in stations))
        if key==self.key:return
        first=self.key is None;self.key=key;self.scene.clear();c=THEMES[theme];self.view.setBackgroundBrush(QColor(c['panel']));positions={};station_positions={};group_heights={};layout_y=0
        for start in range(0,len(stations),4):
            group=stations[start:start+4];height=max([230]+[((sum(d.station_id==st.id for d in devices)+1)//2)*85+50 for st in group])
            for col,st in enumerate(group):station_positions[st.id]=(col*260,layout_y);group_heights[st.id]=height
            layout_y+=height+35
        for s in stations:
            x,y=station_positions[s.id];group=self.scene.addRect(x-10,y-15,245,group_heights[s.id],QPen(QColor(c['line'])),QBrush(QColor(c['raised'])));group.setZValue(-2);label=self.scene.addSimpleText(s.name);label.setBrush(QColor(c['text']));label.setPos(x,y-10)
            station_node=Node(QRectF(x-5,y-15,235,35),lambda station_id=s.id:self.w.map_page.select(station_id));station_node.setPen(QPen(QColor(c['line'])));station_node.setBrush(QBrush(Qt.NoBrush));station_node.setZValue(1);station_node.setToolTip('Select station to manage its radios');self.scene.addItem(station_node)
        counts={};unassigned_y=layout_y
        for d in devices:
            count=counts.get(d.station_id,0);counts[d.station_id]=count+1
            if d.station_id in station_positions:
                x,y=station_positions[d.station_id];positions[d.id]=(x+(count%2)*115,y+30+(count//2)*85)
            else:positions[d.id]=((count%4)*260,unassigned_y+(count//4)*105)
        lookup={d.id:d for d in devices};links=set();last=[]
        for d in devices:
            for peer in (d.parent,d.peer_id):
                if peer not in positions or peer==d.id:continue
                pair=tuple(sorted((d.id,peer)))
                if pair in links:continue
                links.add(pair);a,b=positions[d.id],positions[peer];observed=[states[d.id],states[peer]];state='No reply' if 'No reply' in observed else 'Warning' if 'Warning' in observed or 'Probe error' in observed else 'Online' if all(v=='Online' for v in observed) else 'Unknown';pen=QPen(QColor(status_color(state,theme)),2)
                if state=='Online' and d.peer_id==peer:
                    wireless=[health[d.id],health[peer]]
                    if 'Critical' in wireless:pen.setColor(QColor(status_color('No reply',theme)))
                    elif any(h in ('Fair','Poor') for h in wireless):pen.setColor(QColor(status_color('Warning',theme)))
                    elif 'Unknown' in wireless:pen.setColor(QColor(status_color('Unknown',theme)))
                if state!='Online':pen.setStyle(Qt.DashLine)
                line=self.scene.addLine(a[0]+52,a[1]+32,b[0]+52,b[1]+32,pen);line.setZValue(-1)
            if states[d.id]=='No reply':
                cursor=d.parent;seen={d.id}
                while cursor in lookup and cursor not in seen:
                    seen.add(cursor)
                    if states[cursor] in ('Online','Warning'):last.append(d.name+' → last observed reachable parent: '+lookup[cursor].name);break
                    cursor=lookup[cursor].parent
        for d in devices:
            x,y=positions[d.id];node=Node(QRectF(x,y,108,72),lambda device=d:self.open_device(device));node.setPen(QPen(QColor(status_color(states[d.id],theme)),2));node.setBrush(QBrush(QColor(c['panel'])));self.scene.addItem(node)
            for j,label in enumerate([d.name[:17],d.host[:18] or 'IP missing',states[d.id]]):
                t=QGraphicsSimpleTextItem(label,node);t.setBrush(QColor(c['text'] if j<2 else status_color(states[d.id],theme)));t.setPos(x+6,y+5+j*20)
            node.setToolTip(d.name+'\n'+d.host+'\nRadio quality: '+health[d.id]+'\nConfigured station/links only')
            if self.query and self.query not in (d.name+' '+d.host+' '+d.location+' '+d.notes).casefold():node.setOpacity(.3)
        self.caption.setText(f'{len(stations)} stations · {len(devices)} nodes · {len(links)} configured links');self.evidence.setText('\n'.join(last[:4]) if last else 'No last-reachable-parent evidence currently observed. Configure parent/peer links in Device Manager.');self.scene.setSceneRect(self.scene.itemsBoundingRect().adjusted(-20,-20,20,20))
        if first:self.fit()
