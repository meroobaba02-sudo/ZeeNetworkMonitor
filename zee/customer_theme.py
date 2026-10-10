"""Consistent Qt themes; map and measurement canvases retain their dark backgrounds."""
from PySide6.QtGui import QColor,QPalette,QPixmap,QPainter,QFont,QLinearGradient
from PySide6.QtCore import Qt,QRectF

THEMES={
 'dark':dict(bg='#091522',panel='#101f30',raised='#172a3e',text='#e7eef8',muted='#a4b5c8',line='#2a4058',accent='#147d8b',selected='#194756'),
 'light':dict(bg='#edf2f7',panel='#ffffff',raised='#e6edf5',text='#152a40',muted='#496078',line='#c5d3e0',accent='#087886',selected='#d2edf0')}

def stylesheet(name='dark'):
    c=THEMES.get(name,THEMES['dark'])
    return '''
QWidget {background:%(bg)s;color:%(text)s;font-family:"Segoe UI";font-size:13px;}
QMainWindow,QDialog,QScrollArea {background:%(bg)s;}
QLabel {background:transparent;}
QLabel#title {font-size:24px;font-weight:700;}
QLabel#subtitle,QLabel#muted {color:%(muted)s;}
QLabel#sectionTitle {font-size:16px;font-weight:700;}
QLabel#metricValue {font-size:27px;font-weight:700;}
QLabel#card,QLabel#mapCard {background:%(panel)s;border:1px solid %(line)s;border-radius:9px;padding:12px;font-size:16px;font-weight:600;}
QLabel#mapEvents {background:%(panel)s;border:1px solid %(line)s;border-radius:8px;padding:10px;color:%(muted)s;}
QLabel#detailTitle {font-size:20px;font-weight:700;}
QFrame#metricCard,QFrame#wanCard,QFrame#setupCard {background:%(panel)s;border:1px solid %(line)s;border-radius:10px;}
QGroupBox {border:1px solid %(line)s;border-radius:8px;margin-top:17px;padding:14px;font-weight:600;}
QGroupBox::title {subcontrol-origin:margin;left:12px;padding:0 5px;}
QPushButton {background:%(raised)s;border:1px solid %(line)s;padding:8px 11px;border-radius:6px;min-height:18px;}
QPushButton:hover {border-color:%(accent)s;}
QPushButton:focus,QLineEdit:focus,QComboBox:focus,QSpinBox:focus,QTableWidget:focus {border:2px solid %(accent)s;}
QPushButton:disabled {color:%(muted)s;}
QPushButton#primary {background:%(accent)s;color:white;font-weight:600;}
QPushButton#nav {text-align:left;border:0;padding:10px;background:transparent;}
QPushButton#nav:checked {background:%(selected)s;border-left:3px solid %(accent)s;font-weight:600;}
QLineEdit,QComboBox,QSpinBox,QDoubleSpinBox,QTextEdit,QDateTimeEdit {background:%(panel)s;border:1px solid %(line)s;border-radius:5px;padding:6px;selection-background-color:%(accent)s;}
QTableWidget {background:%(panel)s;alternate-background-color:%(raised)s;gridline-color:%(line)s;border:1px solid %(line)s;border-radius:6px;}
QHeaderView::section {background:%(raised)s;padding:7px;border:0;font-weight:600;}
QTableWidget::item:selected {background:%(selected)s;color:%(text)s;}
QTabBar::tab {background:%(raised)s;padding:9px;margin:2px;}
QTabBar::tab:selected {background:%(accent)s;color:white;}
QCheckBox {spacing:7px;}
QCheckBox::indicator {width:16px;height:16px;}
QToolTip {background:%(panel)s;color:%(text)s;border:1px solid %(line)s;padding:6px;}
QScrollBar:vertical {background:%(bg)s;width:12px;}
QScrollBar::handle:vertical {background:%(line)s;min-height:25px;border-radius:5px;}
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical {height:0;}
'''%c

def apply_theme(app,name):
    if app.property('zee_theme')==name:return
    app.setProperty('zee_theme',name)
    c=THEMES.get(name,THEMES['dark']);palette=QPalette()
    for role,key in [(QPalette.Window,'bg'),(QPalette.Base,'panel'),(QPalette.AlternateBase,'raised'),(QPalette.WindowText,'text'),(QPalette.Text,'text'),(QPalette.Button,'raised'),(QPalette.ButtonText,'text'),(QPalette.Highlight,'accent')]:palette.setColor(role,QColor(c[key]))
    palette.setColor(QPalette.HighlightedText,QColor('#ffffff'));app.setPalette(palette);app.setStyleSheet(stylesheet(name))

def splash_pixmap(version,dpr=1):
    dpr=max(1,min(4,dpr));pix=QPixmap(round(620*dpr),round(230*dpr));pix.setDevicePixelRatio(dpr);pix.fill(QColor('#091522'))
    p=QPainter(pix);p.setRenderHint(QPainter.Antialiasing)
    gradient=QLinearGradient(0,0,620,230);gradient.setColorAt(0,QColor('#12394a'));gradient.setColorAt(1,QColor('#091522'));p.fillRect(QRectF(0,0,620,230),gradient)
    p.setPen(QColor('#65d7d1'));p.setFont(QFont('Segoe UI',12,QFont.Bold));p.drawText(32,45,'ZEE / NETWORK MONITOR')
    p.setPen(QColor('#eef5ff'));p.setFont(QFont('Segoe UI',24,QFont.Bold));p.drawText(32,93,'Your network. One clear view.')
    p.setFont(QFont('Segoe UI',10));p.setPen(QColor('#b3cbdc'));p.drawText(32,130,'Professional Edition  •  v'+version)
    p.drawText(32,161,'Loading saved devices and monitoring settings…')
    p.drawText(32,203,'Created by Zeeshan Rasool');p.end();return pix


def status_color(state,theme='dark'):
    dark={'Online':'#36d399','Warning':'#fbbf24','No reply':'#fb7185','Probe error':'#fbbf24','Checking':'#60a5fa','Unknown':'#9aacc0','Disabled':'#94a3b8','Unconfigured':'#9aacc0','Degraded':'#fbbf24','Offline':'#fb7185'}
    light={'Online':'#087a51','Warning':'#805600','No reply':'#b4233c','Probe error':'#805600','Checking':'#155db8','Unknown':'#496078','Disabled':'#496078','Unconfigured':'#496078','Degraded':'#805600','Offline':'#b4233c'}
    return (light if theme=='light' else dark).get(state,'#496078' if theme=='light' else '#9aacc0')
