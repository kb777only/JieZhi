"""Non-activating selection chip, hover menu and cursor-adjacent results."""
import time
from pathlib import Path
from PySide6.QtCore import Qt,QTimer,QPoint,QRect,Signal,QSize,QPropertyAnimation,QEasingCurve
from PySide6.QtGui import QCursor,QIcon,QPixmap,QPainter,QColor,QPen
from PySide6.QtWidgets import QApplication,QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QTextBrowser,QFileDialog,QSlider
from .client import asset
from .desktop_surface import X11Pointer,probe_image_rect
from .desktop_styles import STYLE_DIMENSIONS,MAX_WEIGHT,preset
from .theme import QUICK,BASE,SLOW,RISE,MD,LG

CHIP_SIZE=QSize(36,24)
CHIP_ICON=QSize(18,18)
CHIP_STYLE='QPushButton#chip {padding:0;min-width:0;min-height:0;border-radius:12px;}'
CHIP_FADE=BASE
CLICK_SLACK=6
MENU_SLACK=36
STYLE_ARM=.240

# Motion. Everything here opens under the pointer while the user is mid-gesture,
# so the budget is small: past about 150 ms a fade stops reading as polish and
# starts reading as the app being slow to answer. The durations come from the
# window's own scale, so the chip and the window move in the same language.
ENTER=BASE
LEAVE=QUICK
GROW=BASE

TEXT_ACTIONS={'summarize':'Summarize','rewrite':'Rewrite','continue':'Continue writing','explain':'Explain','translate':'Translate','generate':'Generate as an image'}
IMAGE_ACTIONS={'rework':'Rework image','upscale':'Upscale 2×','expand':'Expand image','variations':'Create a variation'}


def place(widget,anchor,offset=QPoint(18,18)):
    screen=QApplication.screenAt(anchor) or QApplication.primaryScreen();r=screen.availableGeometry()
    x=anchor.x()+offset.x();y=anchor.y()+offset.y()
    widget.move(max(r.left(),min(x,r.right()-widget.width())),max(r.top(),min(y,r.bottom()-widget.height())))


def near(widget,cursor,pad):
    return widget.isVisible() and widget.geometry().adjusted(-pad,-pad,pad,pad).contains(cursor)


class Motion:
    """Fade and a short rise for one frameless window.

    The window is shown at full size straight away and only its opacity and
    position are animated, so its buttons are hittable from the first frame.
    RISE stays well inside MENU_SLACK, or a press during the rise would miss.
    """
    def __init__(self,widget,parent):
        self.widget=widget;self.leaving=False;self.then=None
        self.fade=QPropertyAnimation(widget,b'windowOpacity',parent);self.fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.slide=QPropertyAnimation(widget,b'pos',parent);self.slide.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.fade.finished.connect(self.settle)
    def stop(self):
        # Qt does not emit finished() on stop(), so settle() cannot fire here.
        self.leaving=False;self.fade.stop();self.slide.stop()
    def enter(self,moving=True,duration=ENTER):
        self.stop();self.widget.setWindowOpacity(1.0)
        if not moving:self.widget.show();return
        rest=self.widget.pos()
        self.widget.setWindowOpacity(0.0);self.widget.move(rest.x(),rest.y()+RISE);self.widget.show()
        self.fade.setDuration(duration);self.fade.setStartValue(0.0);self.fade.setEndValue(1.0);self.fade.start()
        self.slide.setDuration(duration);self.slide.setStartValue(QPoint(rest.x(),rest.y()+RISE));self.slide.setEndValue(rest);self.slide.start()
    def leave(self,moving=True,then=None):
        if not self.widget.isVisible() or self.leaving:return
        self.stop();self.then=then
        if not moving:self.settle(now=True);return
        self.leaving=True
        self.fade.setDuration(LEAVE);self.fade.setStartValue(self.widget.windowOpacity());self.fade.setEndValue(0.0);self.fade.start()
    def settle(self,now=False):
        if not (self.leaving or now):return
        self.leaving=False;self.widget.hide();self.widget.setWindowOpacity(1.0)
        then=self.then;self.then=None
        if then:then()
    def busy(self):
        """Still on screen, but on its way out and no longer a target."""
        return self.leaving


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
        p=QPainter(self);p.drawPixmap(self.rect(),self.snapshot);p.fillRect(self.rect(),QColor(9,15,30,144))
        if not self.area.isEmpty():
            p.save();p.setClipRect(self.area);p.drawPixmap(self.rect(),self.snapshot);p.restore();p.setPen(QPen(QColor('#7aa0ff'),2));p.drawRect(self.area)
        p.setPen(QColor('white'));p.drawText(24,36,'Outline the image · Esc to cancel')
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


class StylePanel(QWidget):
    """Preset styles, or sliders that blend them. The generated prompt stays hidden."""
    chosen=Signal(dict)
    closed=Signal()
    def __init__(self,weights,spot,moving=True):
        super().__init__();floating(self);self.setFixedWidth(300);self.armed=0.0;self.moving=moving
        box=QVBoxLayout(self);box.setContentsMargins(MD,MD,MD,MD);box.addWidget(QLabel('Rewrite as'))
        self.presets=[]
        for key,label,_ in STYLE_DIMENSIONS:
            b=QPushButton(label);b.clicked.connect(lambda checked=False,k=key:self.pick(preset(k)));box.addWidget(b);self.presets.append(b)
        self.custom=QPushButton('Custom…');self.custom.clicked.connect(self.show_sliders);box.addWidget(self.custom)
        self.sliders={};self.rows=[]
        for key,label,_ in STYLE_DIMENSIONS:
            row=QWidget();line=QHBoxLayout(row);line.setContentsMargins(0,0,0,0)
            name=QLabel(label);name.setFixedWidth(96);line.addWidget(name)
            slider=QSlider(Qt.Orientation.Horizontal);slider.setRange(0,MAX_WEIGHT);slider.setValue(max(0,min(MAX_WEIGHT,int(weights.get(key,0) or 0))))
            reading=QLabel(str(slider.value()));reading.setFixedWidth(18)
            slider.valueChanged.connect(lambda value,target=reading:target.setText(str(value)))
            line.addWidget(slider,1);line.addWidget(reading);row.hide();box.addWidget(row)
            self.sliders[key]=slider;self.rows.append(row)
        self.generate=QPushButton('Generate');self.generate.setObjectName('primary');self.generate.clicked.connect(lambda:self.pick(self.weights()));self.generate.hide();box.addWidget(self.generate)
        self.dismiss=QPushButton('Dismiss');self.dismiss.clicked.connect(self.leave);box.addWidget(self.dismiss)
        # The panel takes the menu's place under the pointer, so it opens with the
        # heading there rather than a button, and ignores a press that lands as it maps.
        self.adjustSize();place(self,spot,QPoint(-24,-12))
        self.motion=Motion(self,self)
        self.grow=QPropertyAnimation(self,b'geometry',self);self.grow.setDuration(GROW);self.grow.setEasingCurve(QEasingCurve.Type.OutCubic)
    def showEvent(self,event):
        self.armed=time.monotonic()+STYLE_ARM;super().showEvent(event)
    def ready(self):return time.monotonic()>=self.armed
    def pick(self,weights):
        if self.ready():self.chosen.emit(weights)
    def leave(self):
        if self.ready():self.motion.leave(self.moving,self.close)
    def show_sliders(self):
        if not self.ready():return
        before=self.geometry()
        for row in self.rows:row.show()
        for b in self.presets:b.hide()
        self.custom.hide();self.generate.show();self.adjustSize()
        # Generate lands roughly where Custom just was, so the panel arms again
        # against a press still in flight, exactly as it does when it opens.
        self.armed=time.monotonic()+STYLE_ARM
        after=self.geometry()
        if not self.moving or after==before:return
        self.setGeometry(before);self.grow.setStartValue(before);self.grow.setEndValue(after);self.grow.start()
    def weights(self):return {key:slider.value() for key,slider in self.sliders.items()}
    def closeEvent(self,event):
        self.closed.emit();super().closeEvent(event)
    def keyPressEvent(self,event):
        if event.key()==Qt.Key.Key_Escape:self.motion.leave(self.moving,self.close)
        else:super().keyPressEvent(event)


class ResultPopup(QWidget):
    stop_requested=Signal()
    closed=Signal()
    def __init__(self,title,anchor,parent=None,moving=True):
        super().__init__(parent);floating(self);self.resize(504,408);self.path=None;self.drag=None;self.moving=moving
        box=QVBoxLayout(self);box.setContentsMargins(18,18,18,18)
        row=QHBoxLayout();self.title=QLabel(title);row.addWidget(self.title,1);close=QPushButton('×');close.setFixedWidth(36);close.clicked.connect(self.dismiss);row.addWidget(close);box.addLayout(row)
        self.status=QLabel('Preparing…');self.status.setWordWrap(True);box.addWidget(self.status)
        self.text=QTextBrowser();self.text.setOpenExternalLinks(False);box.addWidget(self.text,1)
        self.picture=QLabel();self.picture.setAlignment(Qt.AlignmentFlag.AlignCenter);self.picture.hide();box.addWidget(self.picture,1)
        row=QHBoxLayout();self.copy=QPushButton('Copy');self.copy.clicked.connect(self.copy_result);row.addWidget(self.copy)
        self.save=QPushButton('Save…');self.save.clicked.connect(self.save_result);row.addWidget(self.save)
        self.stop=QPushButton('Stop');self.stop.clicked.connect(self.stop_requested);row.addWidget(self.stop);box.addLayout(row)
        self.copy.setEnabled(False);self.save.setEnabled(False);place(self,anchor);self.motion=Motion(self,self)
    def dismiss(self):
        # A result the user waved away fades; a result torn down with the app does not.
        self.motion.leave(self.moving,self.close)
    def show_image(self,path):
        self.path=Path(path);self.text.hide();self.picture.show();self.picture.setPixmap(QPixmap(str(path)).scaled(QSize(456,288),Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation));self.copy.setEnabled(True);self.save.setEnabled(True)
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
        if event.key()==Qt.Key.Key_Escape:self.dismiss()
        else:super().keyPressEvent(event)
    def mousePressEvent(self,event):
        # A frameless result has no title bar, so its body drags the window.
        # A drag begun mid-entry wins: the rise stops rather than fighting the pointer.
        if event.button()==Qt.MouseButton.LeftButton:self.motion.slide.stop();self.drag=event.globalPosition().toPoint()-self.frameGeometry().topLeft()
    def mouseMoveEvent(self,event):
        if self.drag is not None and event.buttons()&Qt.MouseButton.LeftButton:self.move(event.globalPosition().toPoint()-self.drag)
    def mouseReleaseEvent(self,event):
        self.drag=None


class DesktopPopup:
    def __init__(self,host):
        self.host=host;self.pointer=None;self.previous_mask=0;self.hover_since=None;self.context=None;self.anchor=QPoint();self.last_text='';self.expires=0;self.probing=False;self.menu_left=None;self.style_panel=None
        self.chip=QPushButton();self.chip.setObjectName('chip');floating(self.chip,True);self.chip.setFixedSize(CHIP_SIZE);self.chip.setIcon(QIcon(str(asset('jiezhi.svg'))));self.chip.setIconSize(CHIP_ICON);self.chip.setToolTip('Hover for 360 ms for JieZhi actions');self.chip.clicked.connect(self.expand)
        self.chip_motion=Motion(self.chip,host)
        self.menu=QWidget();floating(self.menu);self.menu.setFixedWidth(240);self.menu_box=QVBoxLayout(self.menu);self.menu_box.setContentsMargins(12,12,12,12)
        self.toast=QLabel();floating(self.toast,True);self.toast.setMargin(MD);self.toast.setWordWrap(True);self.toast.setMaximumWidth(456)
        self.menu_motion=Motion(self.menu,host);self.toast_motion=Motion(self.toast,host)
        self.toast_timer=QTimer(host);self.toast_timer.setSingleShot(True);self.toast_timer.timeout.connect(lambda:self.toast_motion.leave(self.moving))
        self.settle=QTimer(host);self.settle.setSingleShot(True);self.settle.setInterval(SLOW);self.settle.timeout.connect(self.selection_ready)
        self.timer=QTimer(host);self.timer.setInterval(36);self.timer.timeout.connect(self.poll)
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
        else:self.timer.stop();self.settle.stop();self.dismiss_style();self.hide(False)
    @property
    def moving(self):
        """Settings' reduced motion switch also stills these windows."""
        return bool(self.host.preferences.get('motion',True))
    def owns(self,window,cursor,pad=CLICK_SLACK):
        """Is the pointer on this window of ours? Qt is asked first, then the geometry
        with a little slack: a press is seen up to one poll late, and by then the pointer
        can have drifted off a 36x24 chip. Dismissing on that sample swallowed the click."""
        widget=QApplication.widgetAt(cursor)
        if widget is not None and widget.window() is window:return True
        return near(window,cursor,pad)
    def live(self,window,motion,cursor,pad=CLICK_SLACK):
        return not motion.busy() and self.owns(window,cursor,pad)
    def mine(self,cursor,pad=CLICK_SLACK):
        return self.live(self.chip,self.chip_motion,cursor,pad) or self.live(self.menu,self.menu_motion,cursor,pad)
    def hide(self,moving=None):
        moving=self.moving if moving is None else moving
        self.chip_motion.leave(moving);self.menu_motion.leave(moving)
        self.hover_since=None;self.menu_left=None;self.context=None
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
        # The old chip goes at once rather than fading out somewhere else while
        # the new one rises: two chips on screen reads as a glitch, not motion.
        self.hide(False);self.context=context;self.anchor=QPoint(anchor);place(self.chip,anchor)
        # The chip appears over someone else's window, so it rises in rather than snapping on.
        self.chip_motion.enter(self.moving,CHIP_FADE);self.chip.raise_()
        self.expires=time.monotonic()+12
    def poll(self):
        if not self.pointer:return
        state=self.pointer.state()
        if not state:return
        mask=state[2];cursor=QCursor.pos();pressed=bool(mask & (1<<8)) and not self.previous_mask & (1<<8)
        if self.previous_mask & (1<<10) and not mask & (1<<10):
            own=QApplication.widgetAt(cursor)
            if not own:self.right_click(cursor,state[:2])
        if pressed:
            if not self.mine(cursor):self.hide()
            panel=self.style_panel
            # A click anywhere else puts the chooser away, the way the menu behaves.
            if panel is not None and panel.isVisible() and panel.ready() and not self.owns(panel,cursor):self.dismiss_style(self.moving)
        self.previous_mask=mask
        if self.menu.isVisible() and not self.menu_motion.busy():
            if self.mine(cursor,MENU_SLACK):self.menu_left=None
            elif self.menu_left is None:self.menu_left=time.monotonic()
            elif time.monotonic()-self.menu_left>=.9:self.hide()
        if self.chip.isVisible() and not self.chip_motion.busy() and not self.menu.isVisible():
            if near(self.chip,cursor,CLICK_SLACK):
                if self.hover_since is None:self.hover_since=time.monotonic()
                elif time.monotonic()-self.hover_since>=.360:self.expand()
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
        # Not connect(self.hide): Qt would pass the button's checked state as `moving`
        # and dismiss the menu instantly instead of fading it.
        close=QPushButton('Dismiss');close.clicked.connect(lambda:self.hide());self.menu_box.addWidget(close)
        self.menu_left=None;self.menu.adjustSize();place(self.menu,self.chip.pos()+QPoint(30,-LG))
        self.menu_motion.enter(self.moving);self.menu.raise_()
    def activate(self,action):
        if self.host.busy:self.notify('JieZhi is busy · finish or stop the current task first',self.anchor,2400);return
        context=dict(self.context);anchor=QPoint(self.anchor);spot=QCursor.pos();self.hide()
        if context['kind']=='text':
            if action=='rewrite':self.choose_style(context,anchor,spot)
            else:self.host.run_desktop_action(action,context,anchor)
            return
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
            QTimer.singleShot(BASE,capture)
        else:QTimer.singleShot(BASE,lambda:self.select_area(anchor,selected))
    def choose_style(self,context,anchor,spot=None):
        """Rewrite always asks for a style first. The chooser opens where the menu was,
        so it is where the pointer already is rather than back at the selection."""
        self.dismiss_style()
        panel=StylePanel(self.host.preferences.get('rewrite_style_weights',{}),spot or QCursor.pos(),self.moving)
        panel.setStyleSheet(self.host.styleSheet())
        def run(weights):
            self.dismiss_style();self.host.run_desktop_action('rewrite',{**context,'style':weights},anchor)
        def gone():
            if self.style_panel is panel:self.style_panel=None
        panel.chosen.connect(run);panel.closed.connect(gone)
        self.style_panel=panel;panel.motion.enter(self.moving);panel.raise_();panel.activateWindow()
        return panel
    def dismiss_style(self,moving=False):
        panel=self.style_panel;self.style_panel=None
        if panel is None:return
        def done():panel.close();panel.deleteLater()
        if moving and panel.isVisible():panel.motion.leave(True,done)
        else:done()
    def select_area(self,anchor,done):
        self.selector=AreaSelector(anchor);self.selector.selected.connect(done);self.selector.show();self.selector.activateWindow()
    def notify(self,text,anchor,timeout=0):
        self.toast_timer.stop();self.toast.setText(text);self.toast.adjustSize();place(self.toast,anchor+QPoint(0,-72))
        if not self.toast.isVisible() or self.toast_motion.busy():self.toast_motion.enter(self.moving)
        self.toast.raise_()
        if timeout:self.toast_timer.start(timeout)
    def close(self):
        self.timer.stop();self.settle.stop();self.toast_timer.stop();self.dismiss_style();self.hide(False);self.toast_motion.leave(False)
        if self.pointer:self.pointer.close();self.pointer=None
