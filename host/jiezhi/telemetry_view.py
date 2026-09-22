from collections import deque
import math
import time
from PySide6.QtCore import Qt,QThread,QTimer,QRectF,QPointF,Signal
from PySide6.QtGui import QColor,QPainter,QPainterPath,QPen
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QDialog,QPlainTextEdit
from .telemetry import Collector,number
from .motion import conceal,present,reveal
from .theme import XS,SM,MD,LG,LABEL,CAPTION,SMALL,HEADING,R_INPUT,R_PANEL,tokens


class Sparkline(QWidget):
    def __init__(self,color,ceiling=None,parent=None):
        super().__init__(parent);self.points=deque(maxlen=180);self.color=QColor(color);self.ceiling=ceiling
        self.dark=False;self.setMinimumHeight(24);self.setMaximumHeight(36)
    def add(self,at,value):self.points.append((at,value));self.update()
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect=QRectF(3,3,max(3,self.width()-6),max(3,self.height()-6))
        t=tokens(self.dark)
        p.setPen(QPen(QColor(t['line']),1));p.drawLine(rect.bottomLeft(),rect.bottomRight())
        valid=[v for _,v in self.points if v is not None and math.isfinite(v)]
        if not self.points or not valid:
            p.setPen(QColor(t['ink_3']));p.drawText(rect,Qt.AlignmentFlag.AlignCenter,'No data');return
        end=self.points[-1][0];start=end-120
        hi=self.ceiling or max(1,max(valid)*1.12);lo=0
        path=QPainterPath();drawing=False
        for at,value in self.points:
            if at<start:continue
            if value is None:drawing=False;continue
            point=QPointF(rect.left()+(at-start)/120*rect.width(),rect.bottom()-max(0,min(1,(value-lo)/(hi-lo)))*rect.height())
            if drawing:path.lineTo(point)
            else:path.moveTo(point);drawing=True
        p.setPen(QPen(self.color,2));p.drawPath(path)


class MetricCard(QWidget):
    def __init__(self,title,color,unit='',ceiling=None):
        super().__init__();self.unit=unit;self.setObjectName('telemetryCard');self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground,True)
        col=QVBoxLayout(self);col.setContentsMargins(SM,SM,SM,SM);col.setSpacing(3)
        faint=tokens(False)['ink_3']
        self.title=QLabel(title);self.title.setStyleSheet(f'font-size:{LABEL}px;color:{faint};background:transparent;');col.addWidget(self.title)
        self.value=QLabel('—');self.value.setStyleSheet(f'font-size:{HEADING}px;font-weight:600;color:{color};background:transparent;');col.addWidget(self.value)
        self.chart=Sparkline(color,ceiling);col.addWidget(self.chart)
        self.note=QLabel('Disconnected');self.note.setStyleSheet(f'font-size:{LABEL}px;color:{faint};background:transparent;');col.addWidget(self.note)
    def recolour(self,color):
        self.value.setStyleSheet(f'font-size:{HEADING}px;font-weight:600;color:{color};background:transparent;')
        self.chart.color=QColor(color);self.chart.update()

    def sample(self,at,value,reason,note=''):
        self.chart.add(at,value);self.value.setText(f'{value:.1f}{self.unit}' if value is not None else '—')
        self.note.setText(note or ('Live' if value is not None else 'Unavailable'));self.setToolTip(reason)


class TelemetryWorker(QThread):
    result=Signal(object);error=Signal(str)
    def __init__(self,collector,target):super().__init__();self.collector=collector;self.target=target
    def run(self):
        try:self.result.emit(self.collector.sample(*self.target))
        except Exception:self.error.emit('Could not read phone telemetry.')


class TelemetryPanel(QWidget):
    """One line of live values, with the graphs a click away.

    The eight cards were on every screen at full height; most of the time the
    numbers are all that is wanted, and the page needs the room more.

    Six graphs, not eight: battery temperature and GPU load were the two the
    phone reports least reliably, and both are still named in Sensor details.
    Their colours are palette tokens rather than fixed hexes, so the charts
    turn with the window: blue for the two numbers that matter, purple for the
    load either processor is under, red for heat, pink for memory.
    """

    TITLES={'tokens':'LIVE ≈ TOK/S','battery':'BATTERY','battery_temp':'BATTERY TEMP',
            'soc_temp':'SOC · CPU PEAK','cpu':'CPU LOAD','gpu':'GPU LOAD',
            'npu':'NPU LOAD','memory':'RAM USED'}
    KEYS=[('tokens','accent','',None),('npu','accent_text','%',100),
          ('cpu','violet','%',100),('battery','violet_text','%',100),
          ('soc_temp','danger','°C',110),('memory','pink',' GiB',None)]
    SUMMARY=[('tokens','tok/s'),('battery','%'),('soc_temp','°C'),('memory',' GiB')]

    def __init__(self,client,parent=None):
        super().__init__(parent);self.client=client;self.collector=Collector();self.worker=None;self.last=None;self.target=None;self.closed=False
        self.dark=False
        self.setObjectName('telemetryPanel');self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground,True)
        outer=QVBoxLayout(self);outer.setContentsMargins(MD,SM,MD,SM);outer.setSpacing(SM)
        head=QHBoxLayout();head.setSpacing(MD)
        self.status=QLabel('PHONE TELEMETRY · Connect a phone');head.addWidget(self.status)
        self.summary=QLabel('—');head.addWidget(self.summary)
        head.addStretch(1)
        self.expand=QPushButton('Show graphs');self.expand.setObjectName('quiet')
        self.expand.setCursor(Qt.CursorShape.PointingHandCursor);self.expand.clicked.connect(self.toggle)
        head.addWidget(self.expand)
        self.details=QPushButton('Sensor details');self.details.setObjectName('quiet')
        self.details.setCursor(Qt.CursorShape.PointingHandCursor);self.details.clicked.connect(self.show_details)
        head.addWidget(self.details);outer.addLayout(head)
        self.graphs=QWidget();self.graphs.setAttribute(Qt.WidgetAttribute.WA_StyledBackground,True)
        row=QHBoxLayout(self.graphs);row.setContentsMargins(0,0,0,XS);row.setSpacing(SM);self.cards={}
        for key,shade,unit,ceiling in self.KEYS:
            card=MetricCard(self.TITLES[key],tokens(False)[shade],unit,ceiling)
            self.cards[key]=card;row.addWidget(card,1)
        outer.addWidget(self.graphs)
        self.graphs.setVisible(bool(getattr(parent,'preferences',{}).get('telemetry_graphs',False)))
        self.expand.setText('Hide graphs' if self.graphs.isVisible() else 'Show graphs')
        self.timer=QTimer(self);self.timer.setInterval(996);self.timer.timeout.connect(self.poll);self.timer.start()

    def toggle(self):
        show=not self.graphs.isVisible()
        reveal(self.graphs) if show else conceal(self.graphs)
        self.expand.setText('Hide graphs' if show else 'Show graphs')
        window=self.window()
        if hasattr(window,'preferences'):
            window.preferences['telemetry_graphs']=show
            from .client import save_json
            save_json(window.preferences_path,window.preferences)

    def write_summary(self,sample):
        if not sample:
            self.summary.setText('—');return
        parts=[]
        for key,unit in self.SUMMARY:
            value=sample['values'][key]
            parts.append('—' if value is None else f'{value:.1f}{unit}')
        self.summary.setText('  ·  '.join(parts))

    def set_theme(self,dark):
        self.dark=dark;t=tokens(dark)
        self.setStyleSheet(
            f'QWidget#telemetryPanel {{background:{t["panel"]};border-radius:{R_PANEL}px;}}'
            f'QWidget#telemetryCard {{background:{t["surface"]};border:1px solid {t["line"]};border-radius:{R_INPUT}px;}}')
        self.status.setStyleSheet(f'color:{t["ink_3"]};font-size:{LABEL}px;background:transparent;letter-spacing:3px;')
        self.summary.setStyleSheet(f'color:{t["ink"]};font-size:{SMALL}px;font-weight:600;background:transparent;')
        for (key,shade,_unit,_ceiling),card in zip(self.KEYS,self.cards.values()):
            card.title.setStyleSheet(f'font-size:{LABEL}px;color:{t["ink_3"]};background:transparent;')
            card.note.setStyleSheet(f'font-size:{LABEL}px;color:{t["ink_3"]};background:transparent;')
            card.chart.dark=dark;card.recolour(t[shade])
    
    def poll(self):
        if self.closed:return
        target=(self.client.serial,self.client.port,self.client.token)
        if not target[0] or not target[1]:
            self.target=None;self.unavailable('Disconnected · no phone telemetry');return
        if self.worker:
            if self.last and time.monotonic()-self.last['at']>4:self.unavailable('Stale · waiting for the phone')
            return # Never queue or overlap USB polls.
        if self.target!=target:
            self.target=target;self.last=None
            for card in self.cards.values():card.chart.points.clear()
        worker=TelemetryWorker(self.collector,target);self.worker=worker
        def accept(result):
            if not self.closed and target==(self.client.serial,self.client.port,self.client.token):self.receive(result)
        worker.result.connect(accept)
        worker.error.connect(lambda error:self.unavailable(error) if not self.closed and target==self.target else None)
        def finish():self.worker=None;worker.deleteLater()
        worker.finished.connect(finish);worker.start()
    def receive(self,sample):
        self.last=sample;app=sample['app'];total=sample['memory_total_gib']
        for key,card in self.cards.items():
            value=sample['values'][key];note=''
            if key=='tokens':
                note=('Prefill…' if app.get('first_token_ms') is None else '2s estimate') if app.get('generating') else ('Recent 2s' if value else 'Idle' if value is not None else 'Update client')
            elif key=='memory':note=f'of {total:.1f} GiB' if total else ''
            elif key=='npu' and value is None:note='Not exposed'
            elif key=='soc_temp' and value is not None:note='Hottest CPU sensor'
            card.sample(sample['at'],value,sample['reasons'][key],note)
        self.write_summary(sample)
        state=sample['notice'] or app.get('state','Connected')
        self.status.setText(f'PHONE TELEMETRY · {state}')
        self.setToolTip('2-minute history · refreshed every second, hardware counters every two')
    def unavailable(self,reason):
        self.last=None;self.status.setText('PHONE TELEMETRY · '+reason);self.write_summary(None)
        for card in self.cards.values():card.sample(time.monotonic(),None,reason,'Disconnected' if 'Disconnected' in reason else 'Unavailable')
    def show_details(self):
        dialog=QDialog(self);dialog.setWindowTitle('Phone telemetry · sources and availability');dialog.resize(780,576)
        layout=QVBoxLayout(dialog);view=QPlainTextEdit();view.setReadOnly(True);layout.addWidget(view)
        sample=self.last
        if not sample:view.setPlainText('Connect and pair the phone to collect telemetry. No values are simulated.')
        else:
            lines=[self.status.text(),'','Each line graph shows the last 120 seconds. Gaps represent missing data.','']
            for key,reason in sample['reasons'].items():lines.append(f"{self.TITLES.get(key,key.upper())}: {reason}")
            app=sample['app'];lines+=['',f"App PSS: {app.get('app_pss_bytes',0)/1024**2:.1f} MiB (sampled every 5 seconds)",f"Thermal severity: {app.get('thermal_status','unavailable')} (Android category, not °C)",f"NPU requested: {app.get('requested_backend')=='npu'}; generation active: {app.get('generating',False)} — neither is a utilization measurement."]
            profile=app.get('last_profile',{})
            if profile:lines.append(f"Last completed runtime profile: {profile.get('tokens_per_second',0):.2f} tokens/s, {profile.get('tokens',0)} tokens")
            lines+=['','Current thermal-HAL sensors (°C):']+[f"  {s['name']}: {s['c']:.1f}" for s in sample['sensors']]
            view.setPlainText('\n'.join(lines))
        close=QPushButton('Close');close.clicked.connect(dialog.accept);layout.addWidget(close);present(dialog)
    def shutdown(self):
        self.closed=True;self.timer.stop()
        if self.worker and not self.worker.wait(8000):return False
        self.collector.session.close()
        return True
