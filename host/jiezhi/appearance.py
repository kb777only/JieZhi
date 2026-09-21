"""Local vector artwork and restrained, visibility-aware ambient animation."""
import math
from PySide6.QtCore import Qt,QTimer,QRectF,QPointF
from PySide6.QtGui import QColor,QPainter,QPen,QLinearGradient,QRadialGradient,QPainterPath,QFont
from PySide6.QtWidgets import QWidget

DARK_REPLACEMENTS={'#f3f5fa':'#111522','#202b40':'#e0e7f5','#17253e':'#ecf1ff','#6d7b92':'#9baac4',
 '#eaf0fc':'#191f32','#ffffff':'#1d2539','#e0e6f0':'#34405b','#e8eeff':'#273552','#b8caff':'#617cb2',
 '#dce6ff':'#354a70','#a4aec0':'#75829b','#edf0f6':'#20283a','#e9edf4':'#293249','#b7c8f8':'#344873',
 '#f0f4ff':'#26324c','#dfe8ff':'#30466e','#275ae3':'#b4cbff','#e1e7f1':'#33405a','#d8e4ff':'#385480',
 '#89a7ff':'#759cff','#e3e9f4':'#29324a','#cbd5e7':'#455473','#dfe6f1':'#3c4962'}

def themed_style(base,dark):
    if dark:
        for old,new in DARK_REPLACEMENTS.items():base=base.replace(old,new)
        base=base.replace('background: white','background: #1d2539')
        base+='\nQPushButton#primary {color: #ffffff;} QLabel#brand {color:#7396ff;}'
    return base+'\nQGroupBox {border:1px solid '+('#34405b' if dark else '#e0e6f0')+';border-radius:16px;margin-top:14px;padding:18px;} QGroupBox::title {subcontrol-origin:margin;left:18px;padding:0 6px;} QCheckBox {background:transparent;spacing:8px;} QGraphicsView {border:0;border-radius:20px;} QTabWidget::pane {border:0;} QPushButton#corner {font-size:20px;padding:5px;min-width:32px;max-width:32px;min-height:30px;}'


class DeviceWelcome(QWidget):
    def __init__(self):
        super().__init__();self.dark=False;self.motion=True;self.phase=0;self.phone='Your Android phone';self.soc='USB · private inference'
        self.setMinimumHeight(220);self.setMaximumHeight(260)
        self.timer=QTimer(self);self.timer.setInterval(45);self.timer.timeout.connect(self.tick)
    def tick(self):self.phase+=.015;self.update()
    def showEvent(self,event):
        if self.motion:self.timer.start()
    def hideEvent(self,event):self.timer.stop()
    def configure(self,dark,motion):
        self.dark=dark;self.motion=motion
        if motion and self.isVisible():self.timer.start()
        else:self.timer.stop()
        self.update()
    def device(self,name,soc=''):
        self.phone='Xiaomi 15 Ultra' if '25010' in name else name or 'Your Android phone'
        self.soc=soc or 'USB · private inference';self.update()
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r=QRectF(self.rect());clip=QPainterPath();clip.addRoundedRect(r,24,24);p.setClipPath(clip)
        p.fillRect(r,QColor('#1c2341' if self.dark else '#e7eeff'))
        colors=['#426eff','#aa67e8','#54c5ce']
        for i,color in enumerate(colors):
            x=self.width()*(.18+i*.28)+math.sin(self.phase+i*2)*55;y=self.height()*(.3+i*.17)+math.cos(self.phase*.7+i)*32
            g=QRadialGradient(QPointF(x,y),self.width()*.45);c=QColor(color);c.setAlpha(75 if self.dark else 55);g.setColorAt(0,c);c.setAlpha(0);g.setColorAt(1,c);p.fillRect(r,g)
        p.setPen(QColor('#eef3ff' if self.dark else '#263a63'));p.setFont(QFont('Noto Sans',22,QFont.Weight.Bold))
        p.drawText(QRectF(30,35,max(100,self.width()-340),42),Qt.AlignmentFlag.AlignLeft,'Intelligence, borrowed.')
        p.setFont(QFont('Noto Sans',11));p.drawText(QRectF(32,85,max(100,self.width()-345),70),Qt.TextFlag.TextWordWrap,'Connect your phone. Bring its intelligence\nto a calmer desktop workspace.')
        p.setFont(QFont('Noto Sans',12,QFont.Weight.DemiBold));p.drawText(QRectF(32,165,max(100,self.width()-345),28),Qt.AlignmentFlag.AlignLeft,self.phone)
        p.setFont(QFont('Noto Sans',9));p.drawText(QRectF(32,193,max(100,self.width()-345),22),Qt.AlignmentFlag.AlignLeft,self.soc+' · Device illustration')
        # Original vector device render: front and a camera-equipped back.
        x=self.width()-252;y=18+math.sin(self.phase)*3
        p.setPen(QPen(QColor('#65708d'),1));p.setBrush(QColor('#d8dbe6'));p.drawRoundedRect(QRectF(x+99,y+9,114,204),19,19)
        p.setBrush(QColor('#222631'));p.drawEllipse(QPointF(x+156,y+62),43,43)
        for dx,dy in [(-17,-15),(17,-15),(-17,17),(17,17)]:
            p.setBrush(QColor('#48536b'));p.drawEllipse(QPointF(x+156+dx,y+62+dy),12,12);p.setBrush(QColor('#11192c'));p.drawEllipse(QPointF(x+156+dx,y+62+dy),8,8)
        p.setBrush(QColor('#161d30'));p.drawRoundedRect(QRectF(x,y,111,213),20,20)
        g=QLinearGradient(x,y,x+111,y+210);g.setColorAt(0,QColor('#526af3'));g.setColorAt(.5,QColor('#ac79e9'));g.setColorAt(1,QColor('#64c9da'))
        p.setPen(Qt.PenStyle.NoPen);p.setBrush(g);p.drawRoundedRect(QRectF(x+5,y+5,101,203),16,16)
        p.setBrush(QColor('#192038'));p.drawEllipse(QPointF(x+55,y+13),3,3)
        p.setPen(QColor('white'));p.setFont(QFont('Noto Sans',24,QFont.Weight.Bold));p.drawText(QRectF(x+10,y+70,92,50),Qt.AlignmentFlag.AlignCenter,'借智')
        p.setFont(QFont('Noto Sans',10));p.drawText(QRectF(x+5,y+125,101,30),Qt.AlignmentFlag.AlignCenter,'JieZhi')
