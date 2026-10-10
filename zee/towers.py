from dataclasses import replace
from PySide6.QtWidgets import QDialog,QVBoxLayout,QFormLayout,QLineEdit,QDoubleSpinBox,QCheckBox,QDialogButtonBox,QMessageBox
from .core import Station
from .regionmap import coordinates,position

class TowerDialog(QDialog):
    def __init__(self,parent,station=None,bbox=None):
        super().__init__(parent);self.setWindowTitle('Edit physical tower' if station else 'Add physical tower')
        self.original=station or Station();self.bbox=bbox
        layout=QVBoxLayout(self);form=QFormLayout();layout.addLayout(form)
        self.name=QLineEdit(self.original.name);form.addRow('Tower name',self.name)
        self.height=QDoubleSpinBox();self.height.setRange(0,2000);self.height.setValue(self.original.height);form.addRow('Height (metres, reference)',self.height)
        self.notes=QLineEdit(self.original.notes);form.addRow('Installation notes',self.notes)
        self.gps=QCheckBox('Place using GPS coordinates');self.gps.setChecked(self.original.latitude is not None);form.addRow(self.gps)
        lat,lon=coordinates(self.original.map_x,self.original.map_y,bbox) if bbox else (31.55,69.4)
        self.lat=QDoubleSpinBox();self.lat.setRange(-85,85);self.lat.setDecimals(6);self.lat.setValue(self.original.latitude if self.original.latitude is not None else lat)
        self.lon=QDoubleSpinBox();self.lon.setRange(-180,180);self.lon.setDecimals(6);self.lon.setValue(self.original.longitude if self.original.longitude is not None else lon)
        form.addRow('Latitude',self.lat);form.addRow('Longitude',self.lon)
        self.x=QDoubleSpinBox();self.x.setRange(0,100);self.x.setValue(self.original.map_x*100)
        self.y=QDoubleSpinBox();self.y.setRange(0,100);self.y.setValue(self.original.map_y*100)
        form.addRow('Map X (%)',self.x);form.addRow('Map Y (%)',self.y)
        box=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);box.accepted.connect(self.accept);box.rejected.connect(self.reject);layout.addWidget(box)
    def station(self):
        s=replace(self.original,name=self.name.text(),height=self.height.value(),notes=self.notes.text(),map_x=self.x.value()/100,map_y=self.y.value()/100,latitude=self.lat.value() if self.gps.isChecked() else None,longitude=self.lon.value() if self.gps.isChecked() else None)
        s.validate()
        if self.gps.isChecked() and self.bbox:
            x,y=position(s.latitude,s.longitude,self.bbox)
            if not (0<=x<=1 and 0<=y<=1):raise ValueError('This tower is outside the loaded map. Change map area or use manual placement.')
            s=replace(s,map_x=x,map_y=y)
        return s
    def accept(self):
        try:self.station()
        except ValueError as e:QMessageBox.warning(self,'Check tower',str(e));return
        super().accept()
