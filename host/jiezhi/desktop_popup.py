"""Non-activating selection chip, hover menu and cursor-adjacent results."""
import time
from pathlib import Path
from PySide6.QtCore import Qt,QTimer,QPoint,QRect,Signal,QSize,QPropertyAnimation,QEasingCurve
from PySide6.QtGui import QCursor,QIcon,QPixmap,QPainter,QColor,QPen
from PySide6.QtWidgets import QApplication,QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QTextBrowser,QFileDialog
from .client import asset
from .desktop_surface import X11Pointer,probe_image_rect

CHIP_SIZE=QSize(40,26)
CHIP_ICON=QSize(18,18)
CHIP_STYLE='QPushButton#chip {padding:0;border-radius:8px;}'
CHIP_FADE=140

TEXT_ACTIONS={'summarize':'Summarize','rewrite':'Rewrite','continue':'Continue writing','explain':'Explain','translate':'Translate','generate':'Generate as an image'}
IMAGE_ACTIONS={'rework':'Rework image','upscale':'Upscale 2×','expand':'Expand image','variations':'Create a variation'}


def place(widget,anchor):
    screen=QApplication.screenAt(anchor) or QApplication.primaryScreen();r=screen.availableGeometry()
    widget.move(max(r.left(),min(anchor.x()+18,r.right()-widget.width())),max(r.top(),min(anchor.y()+18,r.bottom()-widget.height())))


def floating(widget,passive=False):
    widget.setWindowFlags(Qt.WindowType.Tool|Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowStaysOnTopHint)
    if passive:
        widget.setWindowFlag(Qt.WindowType.X11BypassWindowManagerHint,True)
        widget.setWindowFlag(Qt.WindowType.WindowDoesNotAcceptFocus,True)
        widget.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)


class AreaSelector(QWidget):
    selected=Signal(object)
    def __init__(self,anchor):
        super().__init__();floating(self)
        self.screen=QApplication.screenAt(anchor) or QApplication.primaryScreen();self.setGeometry(self.screen.geometry())
        self.snapshot=self.screen.grabWindow(0);self.start=None;self.area=QRect();self.setCursor(Qt.CursorShape.CrossCursor)
    def paintEvent(self,event):
        p=QPainter(self);p.drawPixmap(self.rect(),self.snapshot);p.fillRect(self.rect(),QColor(8,15,30,140))
        if not self.area.isEmpty():
            p.save();p.setClipRect(self.area);p.drawPixmap(self.rect(),self.snapshot);p.restore();p.setPen(QPen(QColor('#7aa0ff'),2));p.drawRect(self.area)
        p.setPen(QColor('white'));p.drawText(24,32,'Outline the image · Esc to cancel')
    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:self.start=event.position().toPoint()
        else:self.close()
    def mouseMoveEvent(self,event):
        if self.start is not None:self.area=QRect(self.start,event.position().toPoint()).normalized().intersected(self.rect());self.update()
    def mouseReleaseEvent(self,event):
        if event.button()!=Qt.MouseButton.LeftButton:return
        if self.area.width()>8 and self.area.height()>8:
            scale=self.snapshot.devicePixelRatio();r=QRect(round(self.area.x()*scale),round(self.area.y()*scale),round(self.area.width()*scale),round(self.area.height()*scale))
            image=self.snapshot.copy(r).toImage();image.setDevicePixelRatio(1);self.selected.emit(image)
        self.close()
    def keyPressEvent(self,event):
        if event.key()==Qt.Key.Key_Escape:self.close()


class ResultPopup(QWidget):
    stop_requested=Signal()
    closed=Signal()
    def __init__(self,title,anchor,parent=None):
        super().__init__(parent);floating(self);self.resize(500,410);self.path=None;self.drag=None
        box=QVBoxLayout(self);box.setContentsMargins(18,18,18,18)
        row=QHBoxLayout();self.title=QLabel(title);row.addWidget(self.title,1);close=QPushButton('×');close.setFixedWidth(35);close.clicked.connect(self.close);row.addWidget(close);box.addLayout(row)
        self.status=QLabel('Preparing…');self.status.setWordWrap(True);box.addWidget(self.status)
        self.text=QTextBrowser();self.text.setOpenExternalLinks(False);box.addWidget(self.text,1)
        self.picture=QLabel();self.picture.setAlignment(Qt.AlignmentFlag.AlignCenter);self.picture.hide();box.addWidget(self.picture,1)
        row=QHBoxLayout();self.copy=QPushButton('Copy');self.copy.clicked.connect(self.copy_result);row.addWidget(self.copy)
        self.save=QPushButton('Save…');self.save.clicked.connect(self.save_result);row.addWidget(self.save)
        self.stop=QPushButton('Stop');self.stop.clicked.connect(self.stop_requested);row.addWidget(self.stop);box.addLayout(row)
        self.copy.setEnabled(False);self.save.setEnabled(False);place(self,anchor)
    def show_image(self,path):
        self.path=Path(path);self.text.hide();self.picture.show();self.picture.setPixmap(QPixmap(str(path)).scaled(QSize(455,285),Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation));self.copy.setEnabled(True);self.save.setEnabled(True)
    def copy_result(self):
        if self.path:QApplication.clipboard().setPixmap(QPixmap(str(self.path)))
        else:QApplication.clipboard().setText(self.text.toPlainText())
    def save_result(self):
        name,_=QFileDialog.getSaveFileName(self,'Save result',self.path.name if self.path else 'jiezhi-result.txt')
        if not name:return
        if self.path:
            import shutil
            if Path(name).resolve()!=self.path.resolve():shutil.copyfile(self.path,name)
        else:Path(name).write_text(self.text.toPlainText())
    def closeEvent(self,event):
        self.closed.emit();super().closeEvent(event)
    def keyPressEvent(self,event):
        if event.key()==Qt.Key.Key_Escape:self.close()
        else:super().keyPressEvent(event)
    def mousePressEvent(self,event):
        # A frameless result has no title bar, so its body drags the window.
        if event.button()==Qt.MouseButton.LeftButton:self.drag=event.globalPosition().toPoint()-self.frameGeometry().topLeft()
    def mouseMoveEvent(self,event):
        if self.drag is not None and event.buttons()&Qt.MouseButton.LeftButton:self.move(event.globalPosition().toPoint()-self.drag)
    def mouseReleaseEvent(self,event):
        self.drag=None


class DesktopPopup:
    def __init__(self,host):
        self.host=host;self.pointer=None;self.previous_mask=0;self.hover_since=None;self.context=None;self.anchor=QPoint();self.last_text='';self.expires=0;self.probing=False;self.menu_left=None
        self.chip=QPushButton();self.chip.setObjectName('chip');floating(self.chip,True);self.chip.setFixedSize(CHIP_SIZE);self.chip.setIcon(QIcon(str(asset('jiezhi.svg'))));self.chip.setIconSize(CHIP_ICON);self.chip.setToolTip('Hover for 350 ms for JieZhi actions');self.chip.clicked.connect(self.expand)
        self.fade=QPropertyAnimation(self.chip,b'windowOpacity',host);self.fade.setDuration(CHIP_FADE);self.fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.menu=QWidget();floating(self.menu);self.menu.setFixedWidth(240);self.menu_box=QVBoxLayout(self.menu);self.menu_box.setContentsMargins(12,12,12,12)
        self.toast=QLabel();floating(self.toast,True);self.toast.setMargin(14);self.toast.setWordWrap(True);self.toast.setMaximumWidth(460)
        self.toast_timer=QTimer(host);self.toast_timer.setSingleShot(True);self.toast_timer.timeout.connect(self.toast.hide)
        self.settle=QTimer(host);self.settle.setSingleShot(True);self.settle.setInterval(180);self.settle.timeout.connect(self.selection_ready)
        self.timer=QTimer(host);self.timer.setInterval(40);self.timer.timeout.connect(self.poll)
        QApplication.clipboard().selectionChanged.connect(self.selection_changed)
        self.configure()
    def configure(self):
        for widget in (self.chip,self.menu,self.toast):widget.setStyleSheet(self.host.styleSheet())
        self.chip.setStyleSheet(self.host.styleSheet()+CHIP_STYLE)
        enabled=self.host.preferences.get('desktop_popup',True) and QApplication.platformName()=='xcb'
        if enabled and self.pointer is None:
            try:self.pointer=X11Pointer()
            except Exception:enabled=False
        if enabled:self.timer.start()
        else:self.timer.stop();self.settle.stop();self.hide()
    def hide(self):self.fade.stop();self.chip.hide();self.menu.hide();self.hover_since=None;self.menu_left=None;self.context=None
    def selection_changed(self):
        if self.timer.isActive() and not QApplication.clipboard().ownsSelection():self.settle.start()
    def selection_ready(self):
        if not self.timer.isActive():return
        state=self.pointer.state() if self.pointer else None
        if state and state[2] & (1<<8):self.settle.start();return
        cb=QApplication.clipboard()
        if cb.ownsSelection():return
        text=cb.text(cb.Mode.Selection).strip()
        if text:
            self.last_text=text;self.offer({'kind':'text','text':text[:32000]},QCursor.pos())
    def offer(self,context,anchor):
        self.hide();self.context=context;self.anchor=QPoint(anchor);place(self.chip,anchor)
        # The chip appears over someone else's window, so it fades in rather than snapping on.
        self.chip.setWindowOpacity(0.0);self.chip.show();self.chip.raise_()
        self.fade.setStartValue(0.0);self.fade.setEndValue(1.0);self.fade.start()
        self.expires=time.monotonic()+12
    def poll(self):
        if not self.pointer:return
        state=self.pointer.state()
        if not state:return
        mask=state[2];cursor=QCursor.pos()
        if self.previous_mask & (1<<10) and not mask & (1<<10):
            own=QApplication.widgetAt(cursor)
            if not own:self.right_click(cursor,state[:2])
        if mask & (1<<8) and not self.previous_mask & (1<<8):
            if not self.menu.geometry().contains(cursor) and not self.chip.geometry().contains(cursor):self.hide()
        self.previous_mask=mask
        if self.menu.isVisible():
            if self.menu.geometry().adjusted(-40,-40,40,40).contains(cursor) or self.chip.geometry().adjusted(-40,-40,40,40).contains(cursor):self.menu_left=None
            elif self.menu_left is None:self.menu_left=time.monotonic()
            elif time.monotonic()-self.menu_left>=.9:self.hide()
        if self.chip.isVisible() and not self.menu.isVisible():
            if self.chip.geometry().contains(cursor):
                if self.hover_since is None:self.hover_since=time.monotonic()
                elif time.monotonic()-self.hover_since>=.350:self.expand()
            else:self.hover_since=None
            if time.monotonic()>self.expires:self.hide()
    def right_click(self,anchor,physical):
        if self.probing:return
        from .gui import Worker
        self.probing=True;worker=Worker(lambda _:probe_image_rect(*physical));self.host.workers.add(worker)
        def ready(rect):
            if rect or self.host.preferences.get('image_area_fallback',True):self.offer({'kind':'image','rect':rect,'right_click':True},anchor)
        worker.result.connect(ready)
        def finish():self.probing=False;self.host.workers.discard(worker);worker.deleteLater()
        worker.finished.connect(finish);worker.start()
    def expand(self):
        if not self.context:return
        if self.context.get('right_click'):
            try:self.pointer.dismiss_context_menu()
            except Exception:pass
        while self.menu_box.count():
            item=self.menu_box.takeAt(0)
            if item.widget():item.widget().deleteLater()
        heading=QLabel('Selected text' if self.context['kind']=='text' else ('Detected image' if self.context.get('rect') else 'Image tools · select area'))
        self.menu_box.addWidget(heading)
        if self.host.busy:self.menu_box.addWidget(QLabel('Finish or stop the current task first.'))
        actions=TEXT_ACTIONS if self.context['kind']=='text' else IMAGE_ACTIONS
        for key,title in actions.items():
            b=QPushButton(title);b.setEnabled(not self.host.busy);b.clicked.connect(lambda checked=False,k=key:self.activate(k));self.menu_box.addWidget(b)
        close=QPushButton('Dismiss');close.clicked.connect(self.hide);self.menu_box.addWidget(close)
        self.menu_left=None;self.menu.adjustSize();place(self.menu,self.chip.pos()+QPoint(30,-18));self.menu.show();self.menu.raise_()
    def activate(self,action):
        if self.host.busy:self.notify('JieZhi is busy · finish or stop the current task first',self.anchor,2500);return
        context=dict(self.context);anchor=QPoint(self.anchor);self.hide()
        if context['kind']=='text':self.host.run_desktop_action(action,context,anchor);return
        def selected(image):self.host.run_desktop_action(action,{'kind':'image','image':image},anchor)
        rect=context.get('rect')
        if rect:
            def capture():
                screen=QApplication.screenAt(anchor) or QApplication.primaryScreen()
                # Accessibility extents are device pixels; grabWindow takes logical coordinates.
                ratio=screen.devicePixelRatio();area=[round(value/ratio) for value in rect]
                image=screen.grabWindow(0,*area).toImage()
                if not image.isNull():selected(image)
                else:self.select_area(anchor,selected)
            QTimer.singleShot(150,capture)
        else:QTimer.singleShot(150,lambda:self.select_area(anchor,selected))
    def select_area(self,anchor,done):
        self.selector=AreaSelector(anchor);self.selector.selected.connect(done);self.selector.show();self.selector.activateWindow()
    def notify(self,text,anchor,timeout=0):
        self.toast_timer.stop();self.toast.setText(text);self.toast.adjustSize();place(self.toast,anchor+QPoint(0,-75));self.toast.show();self.toast.raise_()
        if timeout:self.toast_timer.start(timeout)
    def close(self):
        self.timer.stop();self.settle.stop();self.toast_timer.stop();self.hide();self.toast.hide()
        if self.pointer:self.pointer.close();self.pointer=None
