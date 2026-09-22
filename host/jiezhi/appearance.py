"""Local vector artwork and restrained, visibility-aware ambient animation."""
import math
from PySide6.QtCore import Qt,QTimer,QRectF,QPointF
from PySide6.QtGui import QColor,QPainter,QPen,QLinearGradient,QRadialGradient,QPainterPath,QFont
from PySide6.QtWidgets import QWidget,QSizePolicy

from .theme import XS,SM,MD,LG,XL,XXL,BODY,SMALL,CAPTION,TITLE,R_PANEL,tokens,stylesheet


def face(size, weight=QFont.Weight.Normal):
    """Pixel sizes, so the artwork keeps the window's type scale."""
    font = QFont('Noto Sans'); font.setPixelSize(size); font.setWeight(weight); return font


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
        self.setMinimumHeight(252);self.setMaximumHeight(264)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Fixed)
        self.timer=QTimer(self);self.timer.setInterval(48);self.timer.timeout.connect(self.tick)
    def tick(self):self.phase+=.012;self.update()
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
        p.fillRect(r,QColor(t['accent_soft']))
        # Three drifting lights, in the first three colours of the palette.
        colors=[t['accent'],t['violet'],t['pink']]
        for i,color in enumerate(colors):
            x=self.width()*(.18+i*.28)+math.sin(self.phase+i*2)*54;y=self.height()*(.3+i*.18)+math.cos(self.phase*.6+i)*30
            g=QRadialGradient(QPointF(x,y),self.width()*.45);c=QColor(color);c.setAlpha(72 if self.dark else 54);g.setColorAt(0,c);c.setAlpha(0);g.setColorAt(1,c);p.fillRect(r,g)
        column=max(102,self.width()-342);left=XL+SM
        p.setPen(QColor(t['ink']));p.setFont(face(TITLE,QFont.Weight.Bold))
        p.drawText(QRectF(left,XL+SM,column,36),Qt.AlignmentFlag.AlignLeft,'Intelligence, borrowed.')
        p.setPen(QColor(t['ink_2']));p.setFont(face(BODY))
        p.drawText(QRectF(left,72,column,66),Qt.TextFlag.TextWordWrap,'Connect your phone. Bring its intelligence\nto a calmer desktop workspace.')
        p.setPen(QColor(t['ink']));p.setFont(face(BODY,QFont.Weight.DemiBold))
        p.drawText(QRectF(left,162,column,24),Qt.AlignmentFlag.AlignLeft,self.phone)
        p.setPen(QColor(t['ink_3']));p.setFont(face(CAPTION))
        p.drawText(QRectF(left,192,column,24),Qt.AlignmentFlag.AlignLeft,self.soc+' · device illustration')
        # Original vector device render: front and a camera-equipped back. It
        # is centred on the widget so it cannot run past the bottom edge, and
        # a phone is a dark object in either mode, so its chassis is drawn
        # from the dark palette rather than from a grey of its own.
        d = tokens(True)
        x=self.width()-252;y=max(XS,(self.height()-213)/2)+math.sin(self.phase)*3
        p.setPen(QPen(QColor(t['line_strong']),3));p.setBrush(QColor(t['surface_alt']));p.drawRoundedRect(QRectF(x+99,y+9,114,204),19,19)
        p.setBrush(QColor(d['surface']));p.drawEllipse(QPointF(x+156,y+62),43,43)
        for dx,dy in [(-17,-15),(17,-15),(-17,17),(17,17)]:
            p.setBrush(QColor(d['line_strong']));p.drawEllipse(QPointF(x+156+dx,y+62+dy),12,12);p.setBrush(QColor(d['ground']));p.drawEllipse(QPointF(x+156+dx,y+62+dy),9,9)
        p.setBrush(QColor(d['ground']));p.drawRoundedRect(QRectF(x,y,111,213),20,20)
        g=QLinearGradient(x,y,x+111,y+210);g.setColorAt(0,QColor(t['accent']));g.setColorAt(.5,QColor(t['violet']));g.setColorAt(1,QColor(t['pink']))
        p.setPen(Qt.PenStyle.NoPen);p.setBrush(g);p.drawRoundedRect(QRectF(x+5,y+5,101,203),16,16)
        p.setBrush(QColor(d['panel']));p.drawEllipse(QPointF(x+55,y+13),3,3)
        p.setPen(QColor(t['on_accent']));p.setFont(face(36,QFont.Weight.Bold));p.drawText(QRectF(x+12,y+69,90,48),Qt.AlignmentFlag.AlignCenter,'借智')
        p.setFont(face(BODY));p.drawText(QRectF(x+5,y+126,101,30),Qt.AlignmentFlag.AlignCenter,'JieZhi')
