import copy
import threading
from pathlib import Path
import pytest
from jiezhi.workflows import node, validate, WorkflowRunner
from jiezhi.media import MediaClient


def graph(*kinds):
    nodes=[node(k,i*330,50) for i,k in enumerate(kinds)]
    for n in nodes:
        if n['kind'] in {'llm','image','video'}:n['params']['model_id']='model'
    return {'schema':1,'nodes':nodes,'edges':[[a['id'],b['id']] for a,b in zip(nodes,nodes[1:])]}

class FakePhone:
    def __init__(self):self.calls=[]
    def status(self):return {'models':[{'id':'model'}]}
    def load(self,*args):self.calls.append(('load',args))
    def chat(self,messages,emit,max_tokens):
        self.calls.append(('chat',messages));emit({'type':'token','text':'A red teapot.'});emit({'type':'done'})

class FakeMedia:
    def __init__(self):self.calls=[]
    def validate_node(self,n):pass
    def generate(self,n,prompt,inputs,path,cancel,progress):
        self.calls.append((n['kind'],prompt,inputs));return {'type':n['kind'],'path':str(path/'output.png'),'phone_result':'phone.png'}


def test_chained_language_and_image_results(tmp_path):
    g=graph('prompt','llm','image','output');g['nodes'][0]['params']['prompt']='Suggest a subject.'
    phone=FakePhone();media=FakeMedia();events=[]
    result=WorkflowRunner(phone,media,tmp_path,events.append).run(g)
    assert phone.calls[1][1][0]['content']=='Suggest a subject.'
    assert media.calls[0][1]=='A red teapot.'
    assert result[g['nodes'][-1]['id']]['items'][0]['type']=='image'
    assert (tmp_path/'results.json').exists()
    assert [e['state'] for e in events].count('complete')==4


def test_invalid_downstream_is_rejected_before_loading(tmp_path):
    g=graph('llm','llm');g['nodes'][1]['params']['max_tokens']=999999
    phone=FakePhone()
    with pytest.raises(ValueError,match='max_tokens'):WorkflowRunner(phone,FakeMedia(),tmp_path).run(g)
    assert phone.calls==[]
    g['nodes'][1]['params']['max_tokens']=20;g['nodes'][1]['params']['model_id']='missing'
    with pytest.raises(ValueError,match='missing'):WorkflowRunner(phone,FakeMedia(),tmp_path).run(g)
    assert phone.calls==[]


def test_graph_rejects_cycles_media_to_text_and_nonfinite_positions():
    g=graph('llm','llm');g['edges'].append(list(reversed(g['edges'][0])))
    with pytest.raises(ValueError,match='cycle'):validate(g)
    with pytest.raises(ValueError,match='text-only'):validate(graph('image','llm'))
    g=graph('prompt');g['nodes'][0]['x']=float('nan')
    with pytest.raises(ValueError,match='position'):validate(g)


def test_cancel_after_load_never_sends_prompt(tmp_path):
    phone=FakePhone();cancel=threading.Event();phone.load=lambda *args:cancel.set()
    with pytest.raises(RuntimeError,match='stopped'):WorkflowRunner(phone,FakeMedia(),tmp_path,cancelled=cancel).run(graph('llm'))
    assert phone.calls==[]


def test_media_params_validate_before_http():
    media=MediaClient(None);n=node('video');n['params'].update(encoder_id='enc',vae_id='vae',cfg=float('nan'))
    with pytest.raises(ValueError,match='Guidance'):media.validate_node(n)
    n['params'].update(cfg=7,frames=6,backend='cpu',width=256,height=256)
    with pytest.raises(ValueError,match='frame count'):media.validate_node(n)
    n['params'].update(frames=49,backend='npu')
    with pytest.raises(ValueError,match='1024'):media.validate_node(n)


def test_npu_media_requires_converted_packages():
    from types import SimpleNamespace
    info={'available':True,'backends':['cpu','npu'],'models':[{'id':'image','format':'qnn'},{'id':'video','format':'neodragon'},{'id':'gguf','format':'gguf'}]}
    client=SimpleNamespace(request=lambda *a,**k:SimpleNamespace(json=lambda:info))
    media=MediaClient(client);n=node('image');n['params']['model_id']='image';media.validate_node(n)
    n['params']['model_id']='gguf'
    with pytest.raises(ValueError,match='GGUF cannot'):media.validate_node(n)
    n=node('video');n['params']['model_id']='video';media.validate_node(n)
    n['params']['frames']=9
    with pytest.raises(ValueError,match='49-frame'):media.validate_node(n)


def test_canvas_wires_autosave_theme_and_telemetry(qtbot,tmp_path,monkeypatch):
    import jiezhi.gui as gui
    from jiezhi.hub import Hub
    from jiezhi.workflow_view import FlowNode
    monkeypatch.setattr(gui,'DATA',tmp_path)
    monkeypatch.setattr(gui.Window,'start_scan',lambda s:None)
    monkeypatch.setattr(Hub,'restore',lambda s:{})
    w=gui.Window();qtbot.addWidget(w);w.show();w.nav.setCurrentRow(7);qtbot.wait(250)
    canvas=w.flow_canvas
    assert canvas.transform().m11()>.5
    nodes=list(canvas.nodes.values());nodes[0].setSelected(True)
    w.flow_editors['prompt'].setPlainText('Remember this edit')
    canvas.scene_obj.clearSelection();nodes[1].setSelected(True)
    assert nodes[0].data['params']['prompt']=='Remember this edit'
    w.flow_add('image');image=w.flow_selected
    canvas.begin_wire(nodes[1].output);canvas.end_wire(image.input.scenePos())
    assert [nodes[1].data['id'],image.data['id']] in canvas.edges
    w.save_flow_draft();saved=copy.deepcopy(w.flow_graph())
    canvas.load(saved);w.flow_inspect();assert len(canvas.nodes)==4
    w.toggle_dark();assert w.dark and canvas.dark
    w.telemetry_choice.setChecked(False);assert not w.telemetry_panel.timer.isActive()
    w.motion_choice.setChecked(False);assert not w.welcome_art.timer.isActive()
    w.default_context.setValue(4096)
    qtbot.waitUntil(lambda:not w.workers);w.close()
    reopened=gui.Window();qtbot.addWidget(reopened)
    assert reopened.dark and reopened.context.value()==4096
    assert not reopened.telemetry_panel.timer.isActive()
    reopened.close()
