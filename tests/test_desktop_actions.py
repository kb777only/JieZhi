from PySide6.QtCore import QPoint
from jiezhi.gui import Window
import jiezhi.gui as gui
import jiezhi.hub as hub
import jiezhi.desktop_popup as popup
import jiezhi.desktop_styles as styles


def window(qtbot,tmp_path,monkeypatch):
    monkeypatch.setattr(gui,'DATA',tmp_path/'data');monkeypatch.setattr(Window,'start_scan',lambda s:None);monkeypatch.setattr(hub.Hub,'restore',lambda s:{})
    w=Window();qtbot.addWidget(w);w.show();qtbot.wait(250);return w


def test_hover_waits_360ms_and_exposes_context_actions(qtbot,tmp_path,monkeypatch):
    w=window(qtbot,tmp_path,monkeypatch);p=w.desktop_popup
    class Pointer:
        def state(self):return (10,10,0)
        def close(self):pass
    p.pointer=Pointer();clock=[100.0];monkeypatch.setattr(popup.time,'monotonic',lambda:clock[0])
    p.offer({'kind':'text','text':'Selected passage'},QPoint(400,200))
    monkeypatch.setattr(popup.QCursor,'pos',lambda:p.chip.geometry().center())
    p.poll();clock[0]+=.359;p.poll();assert not p.menu.isVisible()
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
    clock[0]+=.5;p.poll();qtbot.waitUntil(lambda:not p.menu.isVisible())
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


def test_chip_is_compact_and_fades_in(qtbot,tmp_path,monkeypatch):
    w=window(qtbot,tmp_path,monkeypatch);p=w.desktop_popup
    assert p.chip.width()>p.chip.height() and p.chip.width()<42
    p.offer({'kind':'text','text':'Selected passage'},QPoint(400,200))
    assert p.chip.windowOpacity()<1 and p.chip_motion.fade.state()==popup.QPropertyAnimation.State.Running
    qtbot.waitUntil(lambda:p.chip_motion.fade.state()==popup.QPropertyAnimation.State.Stopped)
    assert p.chip.windowOpacity()==1
    w.close()


def test_rewrite_asks_for_a_style_before_running(qtbot,tmp_path,monkeypatch):
    w=window(qtbot,tmp_path,monkeypatch);p=w.desktop_popup;calls=[]
    monkeypatch.setattr(w,'run_desktop_action',lambda action,context,anchor:calls.append((action,context)))
    p.offer({'kind':'text','text':'Original passage'},QPoint(400,200));p.activate('rewrite')
    assert calls==[] and p.style_panel.isVisible()
    keys=[key for key,_,_ in styles.STYLE_DIMENSIONS];qtbot.waitUntil(p.style_panel.ready)
    p.style_panel.presets[keys.index('professionalism')].click()
    assert calls[0][0]=='rewrite'
    assert calls[0][1]['style']['professionalism']==styles.MAX_WEIGHT and calls[0][1]['style']['comedy']==0
    w.close()


def test_custom_reveals_sliders_and_generates_a_blend(qtbot,tmp_path,monkeypatch):
    w=window(qtbot,tmp_path,monkeypatch);p=w.desktop_popup;calls=[]
    monkeypatch.setattr(w,'run_desktop_action',lambda action,context,anchor:calls.append(context['style']))
    p.offer({'kind':'text','text':'Original passage'},QPoint(400,200));p.activate('rewrite')
    panel=p.style_panel;assert not panel.generate.isVisible();qtbot.waitUntil(panel.ready)
    panel.custom.click();assert panel.generate.isVisible() and panel.rows[0].isVisible()
    qtbot.waitUntil(panel.ready)
    panel.sliders['comedy'].setValue(7);panel.sliders['warmth'].setValue(3);panel.generate.click()
    assert calls[0]['comedy']==7 and calls[0]['warmth']==3 and calls[0]['professionalism']==0
    w.close()


def test_rewrite_style_shapes_the_prompt_and_is_remembered(qtbot,tmp_path,monkeypatch):
    w=window(qtbot,tmp_path,monkeypatch)
    status={'loaded_id':'a','context_size':8192,'models':[{'id':'a','name':'A'}]}
    w.current_status=status;w.client.status=lambda:status;sent=[]
    def chat(messages,emit,max_tokens):
        sent.extend(messages);emit({'type':'done','profile':{'tokens_per_second':1}})
    w.client.chat=chat;monkeypatch.setattr(w,'update_status',lambda s:None)
    monkeypatch.setattr(w.desktop_popup,'notify',lambda text,*a:None)
    w.run_desktop_action('rewrite',{'kind':'text','text':'Passage','style':{'professionalism':10,'comedy':0}},QPoint(500,300))
    qtbot.waitUntil(lambda:not w.busy)
    assert 'formal professional register' in sent[0]['content'] and 'comed' not in sent[0]['content'].lower()
    assert w.preferences['rewrite_style_weights']['professionalism']==10
    assert 'Professional' in w.quick_result.title.text()
    w.quick_result.close();w.close()


def press(p,cursor,monkeypatch,mask=1<<8):
    """One poll that sees the left button newly down, with the pointer sampled at cursor."""
    class Pointer:
        def state(self):return (0,0,mask)
        def close(self):pass
    monkeypatch.setattr(popup.QCursor,'pos',staticmethod(lambda:cursor))
    p.pointer=Pointer();p.previous_mask=0;p.poll()


def test_a_press_at_the_chip_edge_does_not_swallow_the_click(qtbot,tmp_path,monkeypatch):
    w=window(qtbot,tmp_path,monkeypatch);p=w.desktop_popup
    p.offer({'kind':'text','text':'Selected passage'},QPoint(400,200))
    box=p.chip.geometry()
    press(p,QPoint(box.center().x(),box.bottom()+2),monkeypatch)
    assert p.chip.isVisible()
    p.chip.click();assert p.menu.isVisible()
    w.close()


def test_a_press_away_from_the_chip_still_dismisses_it(qtbot,tmp_path,monkeypatch):
    w=window(qtbot,tmp_path,monkeypatch);p=w.desktop_popup
    p.offer({'kind':'text','text':'Selected passage'},QPoint(400,200))
    box=p.chip.geometry()
    press(p,QPoint(box.center().x(),box.bottom()+140),monkeypatch)
    qtbot.waitUntil(lambda:not p.chip.isVisible())
    w.close()


def test_hover_survives_a_pixel_of_drift(qtbot,tmp_path,monkeypatch):
    w=window(qtbot,tmp_path,monkeypatch);p=w.desktop_popup
    class Pointer:
        def state(self):return (0,0,0)
        def close(self):pass
    p.pointer=Pointer();clock=[100.0];monkeypatch.setattr(popup.time,'monotonic',lambda:clock[0])
    p.offer({'kind':'text','text':'Selected passage'},QPoint(400,200))
    box=p.chip.geometry()
    monkeypatch.setattr(popup.QCursor,'pos',staticmethod(lambda:QPoint(box.center().x(),box.bottom()+2)))
    p.poll();clock[0]+=.4;p.poll()
    assert p.menu.isVisible()
    w.close()


def menu_button(p,label):
    return next(b for b in p.menu.findChildren(popup.QPushButton) if b.text()==label)


def test_the_menu_rewrite_button_opens_the_chooser_rather_than_rewriting(qtbot,tmp_path,monkeypatch):
    """The button the user actually presses, not activate() called directly."""
    w=window(qtbot,tmp_path,monkeypatch);p=w.desktop_popup;calls=[]
    monkeypatch.setattr(w,'run_desktop_action',lambda action,context,anchor:calls.append((action,context)))
    p.offer({'kind':'text','text':'Original passage'},QPoint(400,200));p.expand()
    menu_button(p,'Rewrite').click()
    assert calls==[] and p.style_panel is not None and p.style_panel.isVisible()
    qtbot.waitUntil(lambda:not p.menu.isVisible())
    w.close()


def test_other_text_actions_still_run_straight_away(qtbot,tmp_path,monkeypatch):
    w=window(qtbot,tmp_path,monkeypatch);p=w.desktop_popup;calls=[]
    monkeypatch.setattr(w,'run_desktop_action',lambda action,context,anchor:calls.append(action))
    p.offer({'kind':'text','text':'Original passage'},QPoint(400,200));p.expand()
    menu_button(p,'Summarize').click()
    assert calls==['summarize'] and p.style_panel is None
    w.close()


def test_the_chooser_ignores_the_press_that_opened_it(qtbot,tmp_path,monkeypatch):
    """It opens under the pointer, so a press landing as it maps must not pick a style."""
    w=window(qtbot,tmp_path,monkeypatch);p=w.desktop_popup;calls=[]
    monkeypatch.setattr(w,'run_desktop_action',lambda action,context,anchor:calls.append(context))
    p.offer({'kind':'text','text':'Original passage'},QPoint(400,200));p.activate('rewrite')
    panel=p.style_panel
    panel.presets[0].click();panel.custom.click();panel.dismiss.click()
    assert calls==[] and panel.isVisible() and not panel.generate.isVisible()
    qtbot.waitUntil(panel.ready);panel.presets[0].click()
    assert len(calls)==1
    w.close()


def test_the_chooser_opens_where_the_pointer_is(qtbot,tmp_path,monkeypatch):
    w=window(qtbot,tmp_path,monkeypatch);p=w.desktop_popup
    monkeypatch.setattr(w,'run_desktop_action',lambda *a:None)
    p.offer({'kind':'text','text':'Original passage'},QPoint(400,200));p.expand()
    spot=menu_button(p,'Rewrite').mapToGlobal(QPoint(20,10))
    monkeypatch.setattr(popup.QCursor,'pos',staticmethod(lambda:spot))
    menu_button(p,'Rewrite').click();panel=p.style_panel
    assert panel.geometry().contains(spot), 'the chooser opened away from the pointer'
    assert not any(b.geometry().contains(panel.mapFromGlobal(spot)) for b in panel.presets), 'a preset sits under the pointer'
    w.close()


def test_a_click_away_puts_the_chooser_away(qtbot,tmp_path,monkeypatch):
    w=window(qtbot,tmp_path,monkeypatch);p=w.desktop_popup
    monkeypatch.setattr(w,'run_desktop_action',lambda *a:None)
    p.offer({'kind':'text','text':'Original passage'},QPoint(400,200));p.activate('rewrite')
    panel=p.style_panel;qtbot.waitUntil(panel.ready);gone=[]
    panel.closed.connect(lambda:gone.append(1))
    press(p,panel.geometry().bottomRight()+QPoint(200,200),monkeypatch)
    assert p.style_panel is None
    qtbot.waitUntil(lambda:bool(gone))
    w.close()


def test_a_second_rewrite_replaces_the_first_chooser(qtbot,tmp_path,monkeypatch):
    w=window(qtbot,tmp_path,monkeypatch);p=w.desktop_popup
    monkeypatch.setattr(w,'run_desktop_action',lambda *a:None)
    p.offer({'kind':'text','text':'One'},QPoint(400,200));p.activate('rewrite');first=p.style_panel
    p.offer({'kind':'text','text':'Two'},QPoint(500,300));p.activate('rewrite');second=p.style_panel
    assert second is not first and second.isVisible() and not first.isVisible()
    w.close()


def test_windows_rise_into_place_and_settle(qtbot,tmp_path,monkeypatch):
    w=window(qtbot,tmp_path,monkeypatch);p=w.desktop_popup
    p.offer({'kind':'text','text':'Selected passage'},QPoint(400,200));p.expand()
    rest=p.menu_motion.slide.endValue()
    assert p.menu.pos()!=rest and p.menu_motion.slide.state()==popup.QPropertyAnimation.State.Running
    assert p.menu_motion.slide.startValue().y()-rest.y()==popup.RISE
    qtbot.waitUntil(lambda:p.menu_motion.slide.state()==popup.QPropertyAnimation.State.Stopped)
    assert p.menu.pos()==rest and p.menu.windowOpacity()==1
    w.close()


def test_the_rise_stays_inside_the_slack_a_press_is_forgiven():
    """A window travelling further than the slack would drop a press mid-rise."""
    assert popup.RISE<popup.CLICK_SLACK+popup.MENU_SLACK
    assert popup.ENTER<=150 and popup.LEAVE<=150 and popup.GROW<=150


def test_reduced_motion_makes_every_window_instant(qtbot,tmp_path,monkeypatch):
    w=window(qtbot,tmp_path,monkeypatch);p=w.desktop_popup;w.preferences['motion']=False
    monkeypatch.setattr(w,'run_desktop_action',lambda *a:None)
    running=popup.QPropertyAnimation.State.Running
    p.offer({'kind':'text','text':'Selected passage'},QPoint(400,200))
    assert p.chip.isVisible() and p.chip.windowOpacity()==1 and p.chip_motion.fade.state()!=running
    p.expand();assert p.menu.isVisible() and p.menu_motion.slide.state()!=running
    p.activate('rewrite');assert not p.menu.isVisible() and p.style_panel.windowOpacity()==1
    panel=p.style_panel;qtbot.waitUntil(panel.ready)
    panel.custom.click();assert panel.grow.state()!=running
    p.hide();assert not p.chip.isVisible()
    w.close()


def test_a_window_on_its_way_out_is_not_a_target(qtbot,tmp_path,monkeypatch):
    w=window(qtbot,tmp_path,monkeypatch);p=w.desktop_popup
    p.offer({'kind':'text','text':'Selected passage'},QPoint(400,200));p.expand()
    qtbot.waitUntil(lambda:p.menu_motion.slide.state()==popup.QPropertyAnimation.State.Stopped)
    inside=p.menu.geometry().center();p.hide()
    assert p.menu.isVisible() and not p.mine(inside), 'a fading menu still answered as a target'
    qtbot.waitUntil(lambda:not p.menu.isVisible())
    w.close()


def test_the_chooser_rearms_when_the_sliders_appear(qtbot,tmp_path,monkeypatch):
    """Generate lands where Custom was, so the press that revealed it must not run."""
    w=window(qtbot,tmp_path,monkeypatch);p=w.desktop_popup;calls=[]
    monkeypatch.setattr(w,'run_desktop_action',lambda action,context,anchor:calls.append(context))
    p.offer({'kind':'text','text':'Original passage'},QPoint(400,200));p.activate('rewrite')
    panel=p.style_panel;qtbot.waitUntil(panel.ready)
    panel.custom.click();panel.generate.click()
    assert calls==[]
    qtbot.waitUntil(panel.ready);panel.generate.click()
    assert len(calls)==1
    w.close()


def test_the_menu_dismiss_button_fades_the_menu(qtbot,tmp_path,monkeypatch):
    """clicked passes its checked state, which must not become 'skip the fade'."""
    w=window(qtbot,tmp_path,monkeypatch);p=w.desktop_popup
    p.offer({'kind':'text','text':'Selected passage'},QPoint(400,200));p.expand()
    qtbot.waitUntil(lambda:p.menu_motion.slide.state()==popup.QPropertyAnimation.State.Stopped)
    menu_button(p,'Dismiss').click()
    assert p.menu_motion.busy(), 'the menu vanished instead of fading'
    qtbot.waitUntil(lambda:not p.menu.isVisible())
    w.close()
