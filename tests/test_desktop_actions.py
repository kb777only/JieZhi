from PySide6.QtCore import QPoint
from jiezhi.gui import Window
import jiezhi.gui as gui
import jiezhi.hub as hub
import jiezhi.desktop_popup as popup


def window(qtbot,tmp_path,monkeypatch):
    monkeypatch.setattr(gui,'DATA',tmp_path/'data');monkeypatch.setattr(Window,'start_scan',lambda s:None);monkeypatch.setattr(hub.Hub,'restore',lambda s:{})
    w=Window();qtbot.addWidget(w);w.show();qtbot.wait(250);return w


def test_hover_waits_350ms_and_exposes_context_actions(qtbot,tmp_path,monkeypatch):
    w=window(qtbot,tmp_path,monkeypatch);p=w.desktop_popup
    class Pointer:
        def state(self):return (10,10,0)
        def close(self):pass
    p.pointer=Pointer();clock=[100.0];monkeypatch.setattr(popup.time,'monotonic',lambda:clock[0])
    p.offer({'kind':'text','text':'Selected passage'},QPoint(400,200))
    monkeypatch.setattr(popup.QCursor,'pos',lambda:p.chip.geometry().center())
    p.poll();clock[0]+=.349;p.poll();assert not p.menu.isVisible()
    clock[0]+=.002;p.poll();assert p.menu.isVisible()
    assert p.menu.findChildren(popup.QPushButton)[0].text()=='Summarize'
    w.close()


def test_action_uses_configured_model_streams_and_preserves_settings(qtbot,tmp_path,monkeypatch):
    w=window(qtbot,tmp_path,monkeypatch)
    status={'loaded_id':'a','context_size':8192,'models':[{'id':'a','name':'A'},{'id':'b','name':'B'}]}
    w.current_status=status;w.preferences['desktop_action_models']={'rewrite':'b'};w.fill_desktop_models()
    w.desktop_settings_changed();assert w.preferences['desktop_action_models']['rewrite']=='b'
    loads=[];sent=[];phases=[]
    w.client.status=lambda:status
    def load(key,backend,context):loads.append((key,backend,context));status.update(loaded_id=key);return status
    w.client.load=load;monkeypatch.setattr(w,'update_status',lambda s:None)
    def chat(messages,emit,max_tokens):
        sent.extend(messages);emit({'type':'token','text':'Rewritten passage.'});emit({'type':'done','profile':{'tokens_per_second':30}})
    w.client.chat=chat;monkeypatch.setattr(w.desktop_popup,'notify',lambda text,*a:phases.append(text))
    w.run_desktop_action('rewrite',{'kind':'text','text':'Original passage'},QPoint(500,300))
    qtbot.waitUntil(lambda:not w.busy)
    assert loads==[('b','npu',8192)] and 'Original passage'==sent[-1]['content']
    assert w.quick_result.text.toPlainText()=='Rewritten passage.' and w.quick_result.copy.isEnabled()
    assert phases[0]=='Loading model · B' and phases[1]=='Generating · Rewrite'
    w.quick_result.close();w.run_desktop_action('rewrite',{'kind':'text','text':'Again'},QPoint(500,300));qtbot.waitUntil(lambda:not w.busy)
    assert len(loads)==1
    w.quick_result.close();w.close()


def test_image_right_click_has_area_fallback_and_disable_stops_watching(qtbot,tmp_path,monkeypatch):
    w=window(qtbot,tmp_path,monkeypatch);p=w.desktop_popup
    p.offer({'kind':'image','rect':None},QPoint(400,200));p.expand()
    assert 'Image tools · select area' in [x.text() for x in p.menu.findChildren(popup.QLabel)]
    captured=[];monkeypatch.setattr(p,'select_area',lambda anchor,done:captured.append(anchor))
    p.activate('expand');qtbot.waitUntil(lambda:bool(captured))
    w.desktop_enabled.setChecked(False);assert not p.timer.isActive() and not p.chip.isVisible()
    w.close()


def test_menu_dismisses_when_the_pointer_leaves_it(qtbot,tmp_path,monkeypatch):
    w=window(qtbot,tmp_path,monkeypatch);p=w.desktop_popup
    class Pointer:
        def state(self):return (10,10,0)
        def close(self):pass
    p.pointer=Pointer();clock=[100.0];monkeypatch.setattr(popup.time,'monotonic',lambda:clock[0])
    p.offer({'kind':'text','text':'Selected passage'},QPoint(400,200));p.expand();assert p.menu.isVisible()
    monkeypatch.setattr(popup.QCursor,'pos',lambda:QPoint(1600,1100))
    p.poll();clock[0]+=.5;p.poll();assert p.menu.isVisible()
    clock[0]+=.5;p.poll();assert not p.menu.isVisible()
    w.close()


def test_closed_results_are_released(qtbot,tmp_path,monkeypatch):
    w=window(qtbot,tmp_path,monkeypatch)
    status={'loaded_id':'a','context_size':8192,'models':[{'id':'a','name':'A'}]}
    w.current_status=status;w.client.status=lambda:status
    w.client.chat=lambda messages,emit,max_tokens:emit({'type':'done','profile':{'tokens_per_second':1}})
    monkeypatch.setattr(w,'update_status',lambda s:None);monkeypatch.setattr(w.desktop_popup,'notify',lambda text,*a:None)
    w.run_desktop_action('summarize',{'kind':'text','text':'Passage'},QPoint(500,300));qtbot.waitUntil(lambda:not w.busy)
    assert len(w.quick_results)==1
    w.quick_result.close();assert w.quick_results==[]
    w.close()


def test_detected_image_rect_is_converted_from_device_pixels(qtbot,tmp_path,monkeypatch):
    w=window(qtbot,tmp_path,monkeypatch);p=w.desktop_popup;grabs=[]
    class Screen:
        def devicePixelRatio(self):return 2.0
        def grabWindow(self,window_id,*area):grabs.append(area);return popup.QPixmap(8,8)
    monkeypatch.setattr(w,'run_desktop_action',lambda action,context,anchor:None)
    p.offer({'kind':'image','rect':(100,200,300,400)},QPoint(400,200))
    monkeypatch.setattr(popup.QApplication,'screenAt',lambda point:Screen())
    p.activate('upscale');qtbot.waitUntil(lambda:bool(grabs))
    assert grabs==[(50,100,150,200)]
    w.close()
