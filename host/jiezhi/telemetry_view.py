from collections import deque
import math
import time
from PySide6.QtCore import Qt,QThread,QTimer,QRectF,QPointF,Signal
from PySide6.QtGui import QColor,QPainter,QPainterPath,QPen
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QDialog,QPlainTextEdit
from .telemetry import Collector,number


class Sparkline(QWidget):
    def __init__(self,color,ceiling=None,parent=None):
        super().__init__(parent);self.points=deque(maxlen=180);self.color=QColor(color);self.ceiling=ceiling
        self.setMinimumHeight(26);self.setMaximumHeight(38)
    def add(self,at,value):self.points.append((at,value));self.update()
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect=QRectF(2,2,max(1,self.width()-4),max(1,self.height()-4))
        p.setPen(QPen(QColor('#e4eaf4'),1));p.drawLine(rect.bottomLeft(),rect.bottomRight())
        valid=[v for _,v in self.points if v is not None and math.isfinite(v)]
        if not self.points or not valid:
            p.setPen(QColor('#98a4b8'));p.drawText(rect,Qt.AlignmentFlag.AlignCenter,'No data');return
        end=self.points[-1][0];start=end-120
        hi=self.ceiling or max(1,max(valid)*1.12);lo=0
        path=QPainterPath();drawing=False
        for at,value in self.points:
            if at<start:continue
            if value is None:drawing=False;continue
            point=QPointF(rect.left()+(at-start)/120*rect.width(),rect.bottom()-max(0,min(1,(value-lo)/(hi-lo)))*rect.height())
            if drawing:path.lineTo(point)
            else:path.moveTo(point);drawing=True
        p.setPen(QPen(self.color,1.8));p.drawPath(path)


class MetricCard(QWidget):
    def __init__(self,title,color,unit='',ceiling=None):
        super().__init__();self.unit=unit;self.setObjectName('telemetryCard');self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground,True)
        col=QVBoxLayout(self);col.setContentsMargins(9,6,9,5);col.setSpacing(1)
        self.title=QLabel(title);self.title.setStyleSheet('font-size:11px;color:#6d7b92;background:transparent;');col.addWidget(self.title)
        self.value=QLabel('—');self.value.setStyleSheet(f'font-size:19px;font-weight:600;color:{color};background:transparent;');col.addWidget(self.value)
        self.chart=Sparkline(color,ceiling);col.addWidget(self.chart)
        self.note=QLabel('Disconnected');self.note.setStyleSheet('font-size:10px;color:#8591a7;background:transparent;');col.addWidget(self.note)
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
    def __init__(self,client,parent=None):
        super().__init__(parent);self.client=client;self.collector=Collector();self.worker=None;self.last=None;self.target=None;self.closed=False
        self.setObjectName('telemetryPanel');self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground,True);self.setStyleSheet('QWidget#telemetryPanel {background:#eaf0fc;border-radius:14px;} QWidget#telemetryCard {background:white;border-radius:10px;}')
        outer=QVBoxLayout(self);outer.setContentsMargins(10,6,10,7);outer.setSpacing(4)
        head=QHBoxLayout();self.status=QLabel('PHONE TELEMETRY · Connect a phone');self.status.setStyleSheet('color:#6d7b92;font-size:11px;background:transparent;');head.addWidget(self.status,1)
        self.details=QPushButton('Sensor details');self.details.setStyleSheet('font-size:10px;padding:2px 8px;border-radius:6px;');self.details.clicked.connect(self.show_details);head.addWidget(self.details);outer.addLayout(head)
        row=QHBoxLayout();row.setSpacing(6);self.cards={}
        for key,title,color,unit,ceiling in [
            ('tokens','LIVE ≈ TOK/S','#386bff','',None),('battery','BATTERY','#2b9b82','%',100),
            ('battery_temp','BATTERY TEMP','#e28b3c','°C',70),('soc_temp','SOC · CPU PEAK','#e36b63','°C',110),
            ('cpu','CPU LOAD','#6b7de0','%',100),('gpu','GPU LOAD','#8b67d9','%',100),
            ('npu','NPU LOAD','#ae6dba','%',100),('memory','RAM USED','#368baa',' GiB',None)]:
            card=MetricCard(title,color,unit,ceiling);self.cards[key]=card;row.addWidget(card,1)
        outer.addLayout(row)
        self.timer=QTimer(self);self.timer.setInterval(1000);self.timer.timeout.connect(self.poll);self.timer.start()
    def set_theme(self,dark):
        self.setStyleSheet('QWidget#telemetryPanel {background:'+('#191f32' if dark else '#eaf0fc')+';border-radius:14px;} QWidget#telemetryCard {background:'+('#222c43' if dark else 'white')+';border-radius:10px;}')
        for card in self.cards.values():
            card.title.setStyleSheet('font-size:10px;color:'+('#b2bfd5' if dark else '#6d7b92')+';background:transparent;')
            card.note.setStyleSheet('font-size:10px;color:'+('#a4b4cf' if dark else '#8591a7')+';background:transparent;')
    
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
            elif key=='gpu' and value is None:note='Counter unavailable'
            elif key=='npu' and value is None:note='Not exposed'
            elif key=='soc_temp' and value is not None:note='Hottest CPU sensor'
            card.sample(sample['at'],value,sample['reasons'][key],note)
        state=sample['notice'] or app.get('state','Connected')
        self.status.setText(f'PHONE TELEMETRY · {state} · 2-minute history · 1s refresh / hardware 2s')
    def unavailable(self,reason):
        self.last=None;self.status.setText('PHONE TELEMETRY · '+reason)
        for card in self.cards.values():card.sample(time.monotonic(),None,reason,'Disconnected' if 'Disconnected' in reason else 'Unavailable')
    def show_details(self):
        dialog=QDialog(self);dialog.setWindowTitle('Phone telemetry · sources and availability');dialog.resize(780,580)
        layout=QVBoxLayout(dialog);view=QPlainTextEdit();view.setReadOnly(True);layout.addWidget(view)
        sample=self.last
        if not sample:view.setPlainText('Connect and pair the phone to collect telemetry. No values are simulated.')
        else:
            lines=[self.status.text(),'','Each line graph shows the last 120 seconds. Gaps represent missing data.','']
            for key,reason in sample['reasons'].items():lines.append(f'{self.cards[key].title.text()}: {reason}')
            app=sample['app'];lines+=['',f"App PSS: {app.get('app_pss_bytes',0)/1024**2:.1f} MiB (sampled every 5 seconds)",f"Thermal severity: {app.get('thermal_status','unavailable')} (Android category, not °C)",f"NPU requested: {app.get('requested_backend')=='npu'}; generation active: {app.get('generating',False)} — neither is a utilization measurement."]
            profile=app.get('last_profile',{})
            if profile:lines.append(f"Last completed runtime profile: {profile.get('tokens_per_second',0):.2f} tokens/s, {profile.get('tokens',0)} tokens")
            lines+=['','Current thermal-HAL sensors (°C):']+[f"  {s['name']}: {s['c']:.1f}" for s in sample['sensors']]
            view.setPlainText('\n'.join(lines))
        close=QPushButton('Close');close.clicked.connect(dialog.accept);layout.addWidget(close);dialog.exec()
    def shutdown(self):
        self.closed=True;self.timer.stop()
        if self.worker and not self.worker.wait(8000):return False
        self.collector.session.close()
        return True
