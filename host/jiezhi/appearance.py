"""Local vector artwork and restrained, visibility-aware ambient animation."""
import math
from PySide6.QtCore import Qt,QTimer,QRectF,QPointF
from PySide6.QtGui import QColor,QPainter,QPen,QLinearGradient,QRadialGradient,QPainterPath,QFont
from PySide6.QtWidgets import QWidget,QSizePolicy

from .theme import XS,SM,LG,XL,R_PANEL,tokens,stylesheet

def themed_style(base, dark):
    """Kept as the app's single entry point for the window stylesheet.

    The base argument is ignored: the sheet is generated from the palette in
    theme.py for the requested mode, so a colour can no longer be added to one
    mode and silently missed in the other.
    """
    return stylesheet(dark)


class DeviceWelcome(QWidget):
    def __init__(self):
        super().__init__();self.dark=False;self.motion=True;self.phase=0;self.phone='Your Android phone';self.soc='USB · private inference'
        # The device vector is 213px tall plus its bob; anything shorter clipped it.
        self.setMinimumHeight(248);self.setMaximumHeight(264)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Fixed)
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
        t=tokens(self.dark)
        r=QRectF(self.rect());clip=QPainterPath();clip.addRoundedRect(r,R_PANEL,R_PANEL);p.setClipPath(clip)
        p.fillRect(r,QColor('#1c2341' if self.dark else '#e6ebfb'))
        colors=['#426eff','#aa67e8','#54c5ce']
        for i,color in enumerate(colors):
            x=self.width()*(.18+i*.28)+math.sin(self.phase+i*2)*55;y=self.height()*(.3+i*.17)+math.cos(self.phase*.7+i)*32
            g=QRadialGradient(QPointF(x,y),self.width()*.45);c=QColor(color);c.setAlpha(75 if self.dark else 55);g.setColorAt(0,c);c.setAlpha(0);g.setColorAt(1,c);p.fillRect(r,g)
        column=max(100,self.width()-340);left=XL+SM
        p.setPen(QColor(t['ink']));p.setFont(QFont('Noto Sans',20,QFont.Weight.Bold))
        p.drawText(QRectF(left,XL+SM,column,40),Qt.AlignmentFlag.AlignLeft,'Intelligence, borrowed.')
        p.setPen(QColor(t['ink_2']));p.setFont(QFont('Noto Sans',10))
        p.drawText(QRectF(left,74,column,64),Qt.TextFlag.TextWordWrap,'Connect your phone. Bring its intelligence\nto a calmer desktop workspace.')
        p.setPen(QColor(t['ink']));p.setFont(QFont('Noto Sans',11,QFont.Weight.DemiBold))
        p.drawText(QRectF(left,164,column,26),Qt.AlignmentFlag.AlignLeft,self.phone)
        p.setPen(QColor(t['ink_3']));p.setFont(QFont('Noto Sans',9))
        p.drawText(QRectF(left,190,column,22),Qt.AlignmentFlag.AlignLeft,self.soc+' · device illustration')
        # Original vector device render: front and a camera-equipped back. It is
        # centred on the widget so it cannot run past the bottom edge.
        x=self.width()-252;y=max(XS,(self.height()-213)/2)+math.sin(self.phase)*3
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
