from pathlib import Path
from PySide6.QtCore import Qt
from jiezhi.gui import Window
import jiezhi.gui as gui
import jiezhi.hub as hub


def test_attachment_send_and_reopen(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr(gui, 'DATA', tmp_path / 'data')
    monkeypatch.setattr(hub, 'DATA', tmp_path / 'data')
    monkeypatch.setattr(Window, 'start_scan', lambda self: None)
    monkeypatch.setattr(hub.Hub, 'restore', lambda self: {})
    w = Window(); qtbot.addWidget(w); w.show(); qtbot.wait(250)
    captured = []
    w.current_status = {'loaded_id': 'test', 'loaded_name': 'test.gguf', 'context_size': 2048}
    def chat(messages, emit, max_tokens=512):
        captured.extend(messages)
        emit({'type': 'token', 'text': 'The code is WILLOW-742.'})
        emit({'type': 'done', 'profile': {'tokens_per_second': 30, 'ttft_ms': 100, 'tokens': 8}})
    w.client.chat = chat
    path = tmp_path / 'launch.md'; path.write_text('The launch code is WILLOW-742.')
    w.add_attachments([path]); qtbot.waitUntil(lambda: not w.busy)
    assert len(w.pending_attachments) == 1
    assert w.preview_files.isEnabled()
    w.composer.setPlainText('What is the launch code?')
    qtbot.mouseClick(w.send_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: not w.busy)
    assert 'WILLOW-742' in captured[-1]['content']
    assert not w.pending_attachments
    assert 'launch.md' in w.transcript.toPlainText()
    w.open_chat(w.history.item(0))
    assert w.messages[0]['attachments'][0]['text'] == path.read_text()
    assert w.messages[-1]['content'] == 'The code is WILLOW-742.'
    qtbot.waitUntil(lambda: not w.workers)
    w.close()


def test_assistant_approval_and_stop(qtbot,tmp_path,monkeypatch):
    import json
    import jiezhi.assistant_view as av
    import jiezhi.pc_tools as pc
    from PySide6.QtWidgets import QPushButton
    monkeypatch.setattr(gui,'DATA',tmp_path/'data');monkeypatch.setattr(av,'DATA',tmp_path/'data');monkeypatch.setattr(pc,'DATA',tmp_path/'data')
    monkeypatch.setattr(Window,'start_scan',lambda s:None);monkeypatch.setattr(hub.Hub,'restore',lambda s:{})
    root=tmp_path/'work';root.mkdir();path=root/'config';path.write_text('bad')
    w=Window();qtbot.addWidget(w);w.show();qtbot.wait(250)
    w.current_status={'loaded_id':'fixture','context_size':8192}
    w.pc_roots.clear();w.pc_roots.addItem(str(root));w.pc_request.setPlainText('Fix the config')
    actions=[{'tool':'read_file','args':{'path':str(path)}},{'tool':'edit_file','args':{'path':str(path),'old':'bad','new':'good'}}]
    def chat(messages,emit,max_tokens):emit({'type':'token','text':json.dumps(actions.pop(0))})
    w.client.chat=chat;w.client.cancel=lambda:None
    w.start_assistant()
    qtbot.waitUntil(lambda:w.approval_dialog is not None,timeout=5000)
    assert path.read_text()=='bad'
    assert not w.access_mode.isEnabled()
    qtbot.mouseClick(w.pc_stop,Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda:w.pc_worker is None and not w.workers,timeout=5000)
    assert path.read_text()=='bad' and w.approval_dialog is None
    assert w.access_mode.isEnabled()
    w.close()


def test_project_chat_history_is_separate(qtbot,tmp_path,monkeypatch):
    monkeypatch.setattr(gui,'DATA',tmp_path/'data');monkeypatch.setattr(Window,'start_scan',lambda s:None);monkeypatch.setattr(hub.Hub,'restore',lambda s:{})
    w=Window();qtbot.addWidget(w);w.show();qtbot.wait(250)
    w.messages=[{'role':'user','content':'Personal chat'}];w.save_chat()
    w.active_project={'id':'a'*32,'name':'Launch','folders':[],'documents':[]};w.new_chat()
    w.messages=[{'role':'user','content':'Project chat'}];w.save_chat();w.refresh_history()
    assert w.history.count()==1 and w.history.item(0).text()=='Project chat'
    w.leave_project();assert w.history.count()==1 and w.history.item(0).text()=='Personal chat'
    qtbot.waitUntil(lambda:not w.workers);w.close()


def test_project_chat_creates_and_edits_after_real_approval(qtbot,tmp_path,monkeypatch):
    import json
    import jiezhi.assistant_view as av
    import jiezhi.pc_tools as pc
    from jiezhi.projects import Projects
    monkeypatch.setattr(gui,'DATA',tmp_path/'data');monkeypatch.setattr(av,'DATA',tmp_path/'data');monkeypatch.setattr(pc,'DATA',tmp_path/'data')
    monkeypatch.setattr(Window,'start_scan',lambda s:None);monkeypatch.setattr(hub.Hub,'restore',lambda s:{})
    w=Window();qtbot.addWidget(w);w.show();qtbot.wait(250)
    w.project_store=Projects(tmp_path/'projects',tmp_path/'workspaces')
    w.active_project=w.project_store.create('Snake Game');w.new_chat()
    w.current_status={'loaded_id':'fixture','context_size':2048,'requested_backend':'npu'}
    loads=[]
    def load(*args):
        loads.append(args);return {'loaded_id':'fixture','context_size':8192}
    w.client.load=load;monkeypatch.setattr(w,'update_status',lambda status:setattr(w,'current_status',status))
    path=tmp_path/'workspaces'/('Snake Game-'+w.active_project['id'][:8])/'snake.py'
    actions=[{'tool':'create_file','args':{'path':str(path),'content':'print("snake")\n'}},
             {'answer':'Created snake.py.'}]
    def chat(messages,emit,max_tokens):emit({'type':'token','text':json.dumps(actions.pop(0))})
    w.client.chat=chat;w.client.cancel=lambda:None
    w.composer.setPlainText('Create a snake program in this project.');w.send()
    qtbot.waitUntil(lambda:w.approval_dialog is not None,timeout=5000)
    assert not path.exists() and not w.project_access.isEnabled()
    w.approval_dialog.accept()
    qtbot.waitUntil(lambda:not w.busy,timeout=5000)
    assert path.read_text()=='print("snake")\n' and loads==[('fixture','npu',8192)]
    assert 'Saved · '+str(path) in w.transcript.toPlainText()
    actions.extend([{'tool':'read_file','args':{'path':str(path)}},
        {'tool':'edit_file','args':{'path':str(path),'old':'snake','new':'Snake Game'}}, {'answer':'Updated snake.py.'}])
    w.composer.setPlainText('Change the title to Snake Game.');w.send()
    qtbot.waitUntil(lambda:w.approval_dialog is not None,timeout=5000)
    assert path.read_text()=='print("snake")\n'
    w.approval_dialog.accept();qtbot.waitUntil(lambda:not w.busy,timeout=5000)
    assert path.read_text()=='print("Snake Game")\n' and len(loads)==1
    w.open_chat(w.history.item(0));assert 'Saved · '+str(path) in w.transcript.toPlainText()
    w.close()
