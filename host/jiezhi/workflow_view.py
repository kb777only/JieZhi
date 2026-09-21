import copy,json,math,threading,time
from shiboken6 import isValid
from pathlib import Path
from PySide6.QtCore import Qt,QPointF,QRectF,QTimer,QUrl
from PySide6.QtGui import QColor,QPen,QPainter,QPainterPath,QFont,QDesktopServices,QPixmap
from PySide6.QtWidgets import (QGraphicsView,QGraphicsScene,QGraphicsObject,QGraphicsEllipseItem,QGraphicsPathItem,
 QGraphicsItem,QWidget,QVBoxLayout,QHBoxLayout,QSplitter,QFormLayout,QLineEdit,QPlainTextEdit,QComboBox,QSpinBox,
 QDoubleSpinBox,QPushButton,QFileDialog,QLabel,QScrollArea,QInputDialog,QMessageBox)
from .client import read_json,save_json,asset
from .workflows import KINDS,node,validate,WorkflowRunner
from .media import MediaClient

COLORS={'prompt':'#8e7aed','llm':'#5d8dff','image':'#dc8cce','video':'#48b8b7','output':'#e3a35b'}

class Port(QGraphicsEllipseItem):
    def __init__(self,owner,output):
        super().__init__(-6,-6,12,12,owner);self.owner=owner;self.output=output
        self.setBrush(QColor(COLORS[owner.data['kind']]));self.setPen(QPen(QColor('#eef2ff'),1.5));self.setZValue(3)
        self.setToolTip('Drag to an input to connect' if output else 'Drop a connection here')
    def mousePressEvent(self,event):
        if self.output:self.scene().canvas.begin_wire(self);event.accept()
    def mouseMoveEvent(self,event):
        if self.output:self.scene().canvas.move_wire(event.scenePos());event.accept()
    def mouseReleaseEvent(self,event):
        if self.output:self.scene().canvas.end_wire(event.scenePos());event.accept()

class FlowNode(QGraphicsObject):
    def __init__(self,data,canvas):
        super().__init__();self.data=data;self.canvas=canvas;self.status='Ready'
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsMovable|QGraphicsItem.GraphicsItemFlag.ItemIsSelectable|QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setPos(float(data.get('x',0)),float(data.get('y',0)))
        self.input=Port(self,False) if data['kind']!='prompt' else None
        self.output=Port(self,True) if data['kind']!='output' else None
        if self.input:self.input.setPos(0,65)
        if self.output:self.output.setPos(235,65)
    def boundingRect(self):return QRectF(-8,-2,251,134)
    def paint(self,painter,option,widget):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing);dark=self.canvas.dark
        painter.setBrush(QColor('#222c43' if dark else '#ffffff'));painter.setPen(QPen(QColor('#8cadff' if self.isSelected() else '#394864' if dark else '#d9e2f2'),2 if self.isSelected() else 1))
        painter.drawRoundedRect(QRectF(0,0,235,125),15,15)
        painter.setPen(QColor(COLORS[self.data['kind']]));painter.setFont(QFont('Noto Sans',9,QFont.Weight.Bold));painter.drawText(QRectF(17,12,202,19),KINDS[self.data['kind']].upper())
        painter.setPen(QColor('#e3ebfb' if dark else '#27354f'));painter.setFont(QFont('Noto Sans',11,QFont.Weight.DemiBold));painter.drawText(QRectF(17,36,202,27),self.data['title'][:27])
        p=self.data['params'];hint=p.get('prompt','') if self.data['kind']=='prompt' else 'Phone · '+p.get('backend','') if self.data['kind'] in {'llm','image','video'} else 'Collect connected results'
        painter.setFont(QFont('Noto Sans',9));painter.setPen(QColor('#a5b5ce' if dark else '#76859e'));painter.drawText(QRectF(17,68,202,20),hint.replace('\n',' ')[:32]);painter.drawText(QRectF(17,95,202,20),self.status[:32])
    def itemChange(self,change,value):
        if change==QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self.data['x']=value.x();self.data['y']=value.y();self.canvas.redraw_edges();self.canvas.changed()
        return super().itemChange(change,value)

class FlowCanvas(QGraphicsView):
    def __init__(self,changed):
        self.scene_obj=QGraphicsScene();super().__init__(self.scene_obj);self.scene_obj.canvas=self
        self.dark=False;self.changed=changed;self.nodes={};self.edges=[];self.lines=[];self.wire=None;self.wire_source=None
        self.setRenderHint(QPainter.RenderHint.Antialiasing);self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setSceneRect(-2000,-1500,6000,4000);self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
    def set_theme(self,dark):self.dark=dark;self.setBackgroundBrush(QColor('#151c2d' if dark else '#eef2fa'));self.scene_obj.update()
    def showEvent(self,event):
        super().showEvent(event)
        if not getattr(self,'has_fitted',False):self.has_fitted=True;QTimer.singleShot(0,self.fit)
    def drawBackground(self,painter,rect):
        super().drawBackground(painter,rect);painter.setPen(QPen(QColor('#2b3650' if self.dark else '#d5deef'),1))
        for x in range(math.floor(rect.left()/28)*28,int(rect.right()),28):
            for y in range(math.floor(rect.top()/28)*28,int(rect.bottom()),28):painter.drawPoint(QPointF(x,y))
    def wheelEvent(self,event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            factor=1.15 if event.angleDelta().y()>0 else 1/1.15
            if .25<self.transform().m11()*factor<2.5:self.scale(factor,factor)
            event.accept()
        else:super().wheelEvent(event)
    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.MiddleButton:self.pan=event.position();self.setCursor(Qt.CursorShape.ClosedHandCursor);event.accept();return
        super().mousePressEvent(event)
    def mouseMoveEvent(self,event):
        if hasattr(self,'pan'):
            delta=event.position()-self.pan;self.pan=event.position();self.horizontalScrollBar().setValue(self.horizontalScrollBar().value()-int(delta.x()));self.verticalScrollBar().setValue(self.verticalScrollBar().value()-int(delta.y()));return
        super().mouseMoveEvent(event)
    def mouseReleaseEvent(self,event):
        if hasattr(self,'pan'):del self.pan;self.unsetCursor();return
        super().mouseReleaseEvent(event)
    def load(self,graph):
        self.scene_obj.blockSignals(True);self.nodes={};self.lines=[];self.scene_obj.clear();self.edges=graph['edges'];self.wire=None;self.wire_source=None
        for data in graph['nodes']:
            item=FlowNode(data,self);self.nodes[data['id']]=item;self.scene_obj.addItem(item)
        self.redraw_edges()
        self.scene_obj.blockSignals(False)
    @staticmethod
    def curve(a,b):
        path=QPainterPath(a);offset=max(70,abs(b.x()-a.x())*.5);path.cubicTo(a+QPointF(offset,0),b-QPointF(offset,0),b);return path
    def redraw_edges(self):
        for line in self.lines:self.scene_obj.removeItem(line)
        self.lines=[]
        for a,b in self.edges:
            if a not in self.nodes or b not in self.nodes:continue
            source=self.nodes[a].output;dest=self.nodes[b].input
            if not source or not dest:continue
            line=QGraphicsPathItem(self.curve(source.scenePos(),dest.scenePos()));line.setPen(QPen(QColor(COLORS[self.nodes[a].data['kind']]),2.4));line.setZValue(-1);line.setData(0,(a,b));line.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable,True);self.scene_obj.addItem(line);self.lines.append(line)
    def begin_wire(self,port):
        self.wire_source=port;self.wire=QGraphicsPathItem();self.wire.setPen(QPen(QColor('#7e9eee'),2,Qt.PenStyle.DashLine));self.scene_obj.addItem(self.wire)
    def move_wire(self,pos):
        if self.wire:self.wire.setPath(self.curve(self.wire_source.scenePos(),pos))
    def end_wire(self,pos):
        if not self.wire:return
        targets=[i for i in self.scene_obj.items(pos) if isinstance(i,Port) and not i.output]
        edge=[self.wire_source.owner.data['id'],targets[0].owner.data['id']] if targets else None
        self.scene_obj.removeItem(self.wire);self.wire=None;self.wire_source=None
        if edge:
            candidate={'schema':1,'nodes':[n.data for n in self.nodes.values()],'edges':self.edges+[edge]}
            try:validate(candidate)
            except ValueError as e:self.window().statusBar().showMessage(str(e));return
            self.edges.append(edge);self.redraw_edges();self.changed()
    def fit(self):
        if self.nodes:self.fitInView(self.scene_obj.itemsBoundingRect().adjusted(-70,-90,70,90),Qt.AspectRatioMode.KeepAspectRatio)

class WorkflowView:
    def build_workflows(self):
        from .gui import label,button,DATA
        from .gui import row as controls
        self.flow_path=DATA/'workflows'/'draft.json';self.flow_cancel=threading.Event();self.flow_active=False;self.flow_media_models=[];self.flow_last_dir=None
        self.flow_timer=QTimer(self);self.flow_timer.setSingleShot(True);self.flow_timer.setInterval(450);self.flow_timer.timeout.connect(self.save_flow_draft)
        layout=self.page('Connect ideas. Create something.', 'Chain prompts, phone models and generated media. Drag from an output dot to an input dot.')
        layout.addLayout(controls(label('ADD A NODE','section'),
                                  *[button('＋ '+title,lambda checked=False,k=kind:self.flow_add(k))
                                    for kind,title in KINDS.items()], spacing=8))
        split=QSplitter(Qt.Orientation.Horizontal);self.flow_canvas=FlowCanvas(lambda:self.flow_timer.start());split.addWidget(self.flow_canvas)
        inspector=QWidget();ins=QVBoxLayout(inspector);ins.setContentsMargins(14,0,0,0);inspector.setMinimumWidth(270);inspector.setMaximumWidth(320)
        ins.addWidget(label('NODE SETTINGS','section'));scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QScrollArea.Shape.NoFrame);self.flow_form_body=QWidget();self.flow_form=QFormLayout(self.flow_form_body);scroll.setWidget(self.flow_form_body);ins.addWidget(scroll,1)
        ins.addWidget(button('Apply parameters',self.flow_apply,True));ins.addWidget(button('Remove selected node or wire',self.flow_delete,kind='danger'));split.addWidget(inspector);split.setSizes([800,280]);layout.addWidget(split,1)
        layout.addLayout(controls(button('Fit canvas',self.flow_canvas.fit,kind='quiet'),
                                  button('Save as…',self.flow_export,kind='quiet'),
                                  button('Open flow…',self.flow_import,kind='quiet'),
                                  trailing=(button('Refresh phone models',self.flow_refresh_models,kind='quiet'),
                                            button('Import media weights…',self.flow_import_media,kind='quiet'),
                                            button('Get starter media models…',self.flow_get_starter,kind='quiet'))))
        layout.addWidget(label('NPU: Absolute Reality · Neodragon video  /  CPU: SD 1.5 · Wan','fine'))
        self.flow_log=QPlainTextEdit();self.flow_log.setObjectName('console');self.flow_log.setReadOnly(True);self.flow_log.setMaximumHeight(96)
        self.flow_log.setPlaceholderText('Select a node to configure it. Ctrl+wheel to zoom · middle-drag to pan.')
        self.flow_preview=QLabel();self.flow_preview.setFixedSize(130,96);self.flow_preview.setAlignment(Qt.AlignmentFlag.AlignCenter);self.flow_preview.hide();self.flow_output_file=None
        self.flow_open_result=button('Open result ↗',self.flow_open_result_file,kind='quiet');self.flow_open_result.hide()
        layout.addLayout(controls((self.flow_log,1),self.flow_preview,trailing=(self.flow_open_result,)))
        self.flow_state=label('Draft saved locally · only Run starts inference','fine',True)
        self.flow_stop=button('Stop',self.flow_stop_run);self.flow_stop.setEnabled(False)
        self.flow_run_button=button('Run flow',self.flow_run,True)
        layout.addLayout(controls((self.flow_state,1),trailing=(button('Open outputs',self.flow_open_outputs,kind='quiet'),
                                                               self.flow_stop,self.flow_run_button)))
        graph=read_json(self.flow_path,{})
        try:validate(graph)
        except Exception:
            a=node('prompt',0,50);b=node('llm',330,50);c=node('output',660,50);graph={'schema':1,'nodes':[a,b,c],'edges':[[a['id'],b['id']],[b['id'],c['id']]]}
        self.flow_canvas.load(graph);self.flow_canvas.scene_obj.selectionChanged.connect(self.flow_inspect);self.flow_editors={};self.flow_selected=None
    def flow_graph(self):return {'schema':1,'nodes':[n.data for n in self.flow_canvas.nodes.values()],'edges':self.flow_canvas.edges}
    def save_flow_draft(self):
        if hasattr(self,'flow_canvas'):save_json(self.flow_path,self.flow_graph())
    def flow_add(self,kind):
        if self.flow_active:return
        pos=self.flow_canvas.mapToScene(self.flow_canvas.viewport().rect().center());data=node(kind,pos.x()-110,pos.y()-60);item=FlowNode(data,self.flow_canvas);self.flow_canvas.nodes[data['id']]=item;self.flow_canvas.scene_obj.addItem(item);self.flow_canvas.scene_obj.clearSelection();item.setSelected(True);self.flow_timer.start()
    def flow_inspect(self):
        if not isValid(self.flow_canvas.scene_obj):return
        items=[i for i in self.flow_canvas.scene_obj.selectedItems() if isinstance(i,FlowNode)]
        self.flow_selected=items[0] if len(items)==1 else None
        while self.flow_form.count():
            item=self.flow_form.takeAt(0)
            if item.widget():item.widget().deleteLater()
        self.flow_editors={}
        if not self.flow_selected:return
        n=self.flow_selected.data;p=n['params']
        title=QLineEdit(n['title']);self.flow_form.addRow('Name',title);self.flow_editors['title']=title
        if n['kind']!='output':
            prompt=QPlainTextEdit(p.get('prompt',''));prompt.setMaximumHeight(110);prompt.setPlaceholderText('Use {{input}} for connected text');self.flow_form.addRow('Prompt',prompt);self.flow_editors['prompt']=prompt
        if n['kind'] in {'llm','image','video'}:
            combo=QComboBox();combo.addItem('Choose phone model…','')
            models=self.current_status.get('models',[]) if n['kind']=='llm' else self.flow_media_models
            for m in models:
                if m.get('format')!='data':combo.addItem(m['name'],m['id'])
            if p.get('model_id') and combo.findData(p['model_id'])<0:combo.addItem('Saved model · refresh to verify',p['model_id'])
            combo.setCurrentIndex(max(0,combo.findData(p.get('model_id',''))));self.flow_form.addRow('Model',combo);self.flow_editors['model_id']=combo
            backend=QComboBox()
            for text,key in [('Hexagon NPU','npu'),('Phone CPU','cpu')]:backend.addItem(text,key)
            backend.setCurrentIndex(max(0,backend.findData(p.get('backend','cpu'))));self.flow_form.addRow('Execution',backend);self.flow_editors['backend']=backend
        numbers={'llm':[('context','Context',512,8192),('max_tokens','Max output',1,2048)],'image':[('width','Width',128,1024),('height','Height',128,1024),('steps','Steps',1,50),('seed','Seed',0,2147483647)],'video':[('width','Width',128,512),('height','Height',128,512),('steps','Steps',1,30),('frames','Frames (4n+1)',5,81),('fps','FPS',1,30),('seed','Seed',0,2147483647)]}
        controls=numbers.get(n['kind'],[])
        if n['kind'] in {'image','video'} and p.get('backend')=='npu':
            controls=[c for c in controls if c[0] in ({'steps','seed'} if n['kind']=='image' else {'seed','fps'})]
            self.flow_form.addRow('Pipeline',QLabel('512 × 512 · SD 1.5 QNN' if n['kind']=='image' else '1024 × 640 · 49 frames\nNeodragon fixed schedule'))
        for key,title,lo,hi in controls:
            editor=QSpinBox();editor.setRange(lo,hi);editor.setValue(p.get(key,lo));self.flow_form.addRow(title,editor);self.flow_editors[key]=editor
        if n['kind']=='image' or (n['kind']=='video' and p.get('backend')=='cpu'):
            cfg=QDoubleSpinBox();cfg.setRange(1,20);cfg.setValue(p.get('cfg',7));self.flow_form.addRow('Guidance',cfg);self.flow_editors['cfg']=cfg
            neg=QLineEdit(p.get('negative',''));self.flow_form.addRow('Negative',neg);self.flow_editors['negative']=neg
        if n['kind']=='video':
            mode=QComboBox();mode.addItem('Text → video',False);mode.addItem('Image → video (I2V/VACE)',True);mode.setCurrentIndex(int(bool(p.get('image_conditioned'))));self.flow_form.addRow('Conditioning',mode);self.flow_editors['image_conditioned']=mode
            for key,title in ([] if p.get('backend')=='npu' else [('vae_id','Wan VAE'),('encoder_id','UMT5 encoder'),('vision_id','CLIP vision (I2V)')]):
                combo=QComboBox();combo.addItem('None','')
                for m in self.flow_media_models:combo.addItem(m['name'],m['id'])
                combo.setCurrentIndex(max(0,combo.findData(p.get(key,''))));self.flow_form.addRow(title,combo);self.flow_editors[key]=combo
        for editor in self.flow_editors.values():
            editor.setEnabled(not self.flow_active)
            if isinstance(editor,QComboBox):
                editor.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon);editor.setMinimumContentsLength(12);editor.currentIndexChanged.connect(self.flow_apply)
            elif isinstance(editor,(QSpinBox,QDoubleSpinBox)):editor.valueChanged.connect(self.flow_apply)
            else:editor.textChanged.connect(self.flow_apply)
        if 'backend' in self.flow_editors:self.flow_editors['backend'].currentIndexChanged.connect(self.flow_backend_changed)
    def flow_backend_changed(self):
        if not self.flow_selected or self.flow_active:return
        n=self.flow_selected.data;p=n['params']
        if n['kind'] in {'image','video'}:
            p['model_id']=''
            if n['kind']=='video':p.update(width=1024 if p['backend']=='npu' else 256,height=640 if p['backend']=='npu' else 256,frames=49 if p['backend']=='npu' else 9)
            else:p.update(width=512,height=512)
        self.flow_inspect()
    def flow_apply(self):
        if not self.flow_selected or self.flow_active:return
        n=self.flow_selected.data
        for key,w in self.flow_editors.items():
            value=w.toPlainText() if isinstance(w,QPlainTextEdit) else w.currentData() if isinstance(w,QComboBox) else w.value() if isinstance(w,(QSpinBox,QDoubleSpinBox)) else w.text()
            if key=='title':n['title']=value
            else:n['params'][key]=value
        self.flow_selected.update();self.flow_timer.start()
    def flow_delete(self):
        if self.flow_active:return
        selected=list(self.flow_canvas.scene_obj.selectedItems());remove={i.data['id'] for i in selected if isinstance(i,FlowNode)}
        edges=[list(i.data(0)) for i in selected if isinstance(i,QGraphicsPathItem) and i.data(0)]
        self.flow_canvas.edges[:]=[e for e in self.flow_canvas.edges if e[0] not in remove and e[1] not in remove and e not in edges]
        for key in remove:self.flow_canvas.scene_obj.removeItem(self.flow_canvas.nodes.pop(key))
        self.flow_canvas.redraw_edges();self.flow_inspect();self.flow_timer.start()
    def flow_export(self):
        self.flow_apply();path,_=QFileDialog.getSaveFileName(self,'Save workflow','JieZhi.flow.json','Workflow (*.json)')
        if path:save_json(Path(path),self.flow_graph())
    def flow_import(self):
        if self.flow_active:return
        path,_=QFileDialog.getOpenFileName(self,'Open workflow','','Workflow (*.json)')
        if not path:return
        try:
            if Path(path).stat().st_size>2*1024**2:raise ValueError('Workflow file is too large')
            graph=json.loads(Path(path).read_text());validate(graph);self.flow_selected=None;self.flow_canvas.load(graph);self.flow_inspect();self.flow_canvas.fit();self.save_flow_draft()
        except Exception as e:self.failed(str(e))
    def flow_refresh_models(self):
        if self.busy:return
        if not self.client.port:self.failed('Connect your phone in Welcome & device first.');return
        def done(result):self.update_status(result[0]);self.flow_media_models=result[1];self.flow_inspect()
        self.run_job(lambda _:(self.client.status(),MediaClient(self.client).models()),done,'Reading phone model libraries…')
    def flow_import_media(self):
        if self.busy:return
        if not self.client.port:self.failed('Connect your phone before importing media weights.');return
        path,_=QFileDialog.getOpenFileName(self,'Import media weights or converted QNN package','','Media models (*.gguf *.safetensors *.zip)')
        if not path:return
        self.run_job(lambda w:MediaClient(self.client).upload(Path(path),w.progress.emit),lambda models:(setattr(self,'flow_media_models',models),self.flow_inspect()),'Transferring media weights…')
    def flow_get_starter(self):
        if self.busy:return
        if not self.client.port:self.failed('Connect your phone before downloading a media starter.');return
        catalog=json.loads(asset('media-catalog.json').read_text());choices=[f"{p['name']} · {sum(f['size'] for f in p['files'])/1024**3:.2f} GiB" for p in catalog.values()]
        choice,ok=QInputDialog.getItem(self,'Media starter','Download verified weights to this PC, then transfer over USB:',choices,0,False)
        if not ok:return
        preset=catalog[list(catalog)[choices.index(choice)]];kind=preset.get('kind',list(catalog)[choices.index(choice)]);backend=preset.get('backend','cpu')
        if QMessageBox.question(self,'Download '+preset['name'],f"{preset['license']}\n\nDownloads stay cached on this PC and are copied to the phone. All required components are included. Execution: phone {backend.upper()}.\n\nContinue?")!=QMessageBox.StandardButton.Yes:return
        self.flow_apply();target=self.flow_selected.data['id'] if self.flow_selected and self.flow_selected.data['kind']==kind else None
        self.flow_cancel.clear();self.flow_stop.setEnabled(True)
        def work(w):
            try:
                media=MediaClient(self.client);roles={};parts=[]
                for f in preset['files']:
                    if self.flow_cancel.is_set():raise RuntimeError('Download stopped; select the starter again to resume.')
                    path=self.hub.download(f,w.progress.emit,self.flow_cancel);media.upload(path,w.progress.emit,self.flow_cancel,f.get('format'));roles[f['role']]=f['sha256']
                    if f.get('bundle_path'):parts.append({'id':f['sha256'],'path':f['bundle_path']})
                if parts:roles={'model_id':self.client.request('POST','/media/bundles',json={'kind':preset['bundle'],'files':parts},timeout=(5,60)).json()['id']}
                return media.models(),roles
            finally:w.event.emit({'download_finished':True})
        def done(result):
            self.flow_media_models,roles=result
            item=self.flow_canvas.nodes.get(target)
            if not item:self.flow_add(kind);item=self.flow_selected
            item.data['params'].update(roles);item.data['params']['backend']=backend;item.data['title']=preset['name'].split(' · ')[0]
            if kind=='video':item.data['params'].update(cfg=6.0,steps=20,width=1024 if backend=='npu' else 256,height=640 if backend=='npu' else 256,frames=49 if backend=='npu' else 9,fps=24 if backend=='npu' else 8,image_conditioned=False)
            else:item.data['params'].update(width=512,height=512,steps=20)
            self.flow_canvas.scene_obj.clearSelection();item.setSelected(True);self.flow_inspect();item.update();self.save_flow_draft();self.flow_state.setText('Starter ready · connect a prompt, then Run flow')
        self.run_job(work,done,'Preparing media starter…',events=self.flow_event)
    def flow_run(self):
        if self.busy:return
        self.flow_apply()
        if not self.client.port:self.failed('Connect a phone before running a flow.');return
        graph=copy.deepcopy(self.flow_graph())
        try:validate(graph)
        except Exception as e:self.failed(str(e));return
        from .gui import DATA
        self.flow_last_dir=DATA/'workflows'/'runs'/str(time.time_ns());self.flow_cancel.clear();self.flow_active=True;self.flow_canvas.setInteractive(False);self.flow_stop.setEnabled(True);self.flow_run_button.setEnabled(False);self.flow_log.clear();self.flow_inspect()
        for item in self.flow_canvas.nodes.values():item.status='Queued';item.update()
        runner=WorkflowRunner(self.client,MediaClient(self.client),self.flow_last_dir,cancelled=self.flow_cancel)
        def work(worker):
            runner.emit=worker.event.emit
            try:return runner.run(graph)
            except Exception as e:worker.event.emit({'run_error':str(e)});raise
            finally:worker.event.emit({'finished':True})
        self.run_job(work,lambda _:self.flow_state.setText('Complete · outputs saved locally'),'Running phone workflow…',events=self.flow_event)
    def flow_event(self,e):
        if e.get('download_finished'):self.flow_stop.setEnabled(False);return
        if e.get('run_error'):
            self.flow_state.setText('Stopped' if self.flow_cancel.is_set() else 'Failed · see details');self.flow_log.appendPlainText(e['run_error'])
            for item in self.flow_canvas.nodes.values():
                if item.status not in {'Complete','Ready'}:item.status='Stopped' if self.flow_cancel.is_set() else 'Not completed';item.update()
            return
        if e.get('finished'):
            self.flow_active=False;self.flow_canvas.setInteractive(True);self.flow_stop.setEnabled(False);self.flow_run_button.setEnabled(True);self.flow_inspect();return
        item=self.flow_canvas.nodes.get(e.get('node'))
        if item:item.status=e['state'].capitalize();item.update()
        self.flow_state.setText(e.get('state','').capitalize());self.flow_log.setPlainText(e.get('text','')[-12000:])
        result=e.get('result',{})
        if result.get('path'):
            self.flow_output_file=Path(result['path']);self.flow_preview.show();self.flow_open_result.show()
            if result['type']=='image':self.flow_preview.setPixmap(QPixmap(str(self.flow_output_file)).scaled(130,100,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))
            else:self.flow_preview.clear();self.flow_preview.setText('▶  Generated video')
    def flow_stop_run(self):
        self.flow_cancel.set();self.run_job(lambda _:(MediaClient(self.client).cancel(),self.client.cancel()),message='Stopping workflow…',exclusive=False)
    def flow_open_outputs(self):
        if self.flow_last_dir and self.flow_last_dir.exists():QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.flow_last_dir)))
    def flow_open_result_file(self):
        if self.flow_output_file and self.flow_output_file.exists():QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.flow_output_file)))
