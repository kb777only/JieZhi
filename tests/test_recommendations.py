import pytest
from jiezhi.recommendations import evaluate, ranked, parameters, quantization, GIB, phone_profile
from jiezhi.hub import Hub

PHONE={'soc':'SM8750','ram_gib':14.8,'storage_gib':100,'phone':'Xiaomi 15 Ultra'}
def model(name='Qwen3-1.7B-Q4_0.gguf',size=1.05):
    return {'name':name,'size':size*GIB,'split':False,'metadata':{}}


def test_estimate_uses_calibration_and_requires_supported_hardware():
    a=evaluate(model(),PHONE)
    assert a['recommended'] and 15<a['speed'][0]<a['speed'][1]<60
    assert a['confidence']=='reference-based estimate'
    assert evaluate(model(),{**PHONE,'soc':'unknown'})['speed'] is None
    assert not evaluate(model(),{})['recommended']
    assert evaluate(model('mystery-4B-Q4_0.gguf',2.5),PHONE)['speed'] is None
    assert evaluate(model('Qwen3.5-9B-Q3_K_M.gguf',4.5),PHONE)['speed'] is None
    low=evaluate(model('Qwen2.5-Coder-1.5B-Q4_K_M.gguf'),PHONE)
    assert low['speed'] and low['confidence']=='low-confidence estimate'


def test_categories_change_order_without_claiming_quality():
    models=[model('Qwen3-0.6B-Q4_0.gguf',.36),model('Qwen2.5-Coder-3B-Q4_0.gguf',1.8)]
    assert ranked(models,PHONE,'fast')[0][0]==models[0]
    assert ranked(models,PHONE,'code')[0][0]==models[1]
    assert 'not a quality benchmark' in evaluate(models[0],PHONE)['details']
    sizes=[model(),model('Qwen3-4B-Q4_0.gguf',2.3)]
    assert ranked(sizes,PHONE,'reason')[0][0]==sizes[1]
    assert ranked(sizes,PHONE,'docs')[0][0]==sizes[1]


def test_memory_context_and_file_size_affect_suitability():
    small=evaluate(model('Qwen3-4B-Q4_0.gguf',2.3),PHONE,context=2048)
    large=evaluate(model('Qwen3-4B-Q4_0.gguf',2.3),PHONE,context=8192)
    assert large['memory'][1]>small['memory'][1]
    tight=evaluate(model('Qwen3-4B-Q4_0.gguf',2.3),{**PHONE,'ram_gib':8},context=8192)
    assert not tight['recommended'] and tight['score']<small['score']
    huge=evaluate(model('Qwen3-32B-Q8_0.gguf',33),PHONE)
    assert huge['fit']=='Too large' and huge['speed'] is None
    assert evaluate(model(),{**PHONE,'storage_gib':.1})['blocked']


def test_moe_and_unsupported_files_never_get_recommended():
    assert parameters('Mixtral-8x7B-Q4_0.gguf',{})==56
    assert parameters('Qwen3-30B-A3B-Q4_0.gguf',{})==30
    for m in [model('mmproj-F16.gguf'),{**model(),'split':True},model('Mixtral-8x7B-Q4_0.gguf',28)]:
        assert not evaluate(m,PHONE)['recommended']
    repo={'id':'test/Qwen3-1.7B-GGUF','siblings':[{'rfilename':'Qwen3-1.7B-Q4_0-00001-of-00002.gguf'}]}
    assert evaluate(repo,PHONE)['blocked']
    assert evaluate({'id':'unknown'},PHONE)['memory'] is None
    assert quantization('Qwen3-1.7B-UD-Q4_K_XL.gguf')=='Q4_K_XL'


def test_hub_enrichment_cache_and_revision_are_preserved(monkeypatch):
    h=Hub();calls=[]
    def api(path,**kwargs):
        calls.append(path)
        return {'sha':'a'*40,'gguf':{'total':1_700_000_000,'architecture':'qwen3','chat_template':'do not execute'},
                'siblings':[{'rfilename':'Qwen3-1.7B-Q4_0.gguf','size':100,'lfs':{'sha256':'b'*64}}]}
    monkeypatch.setattr(h,'api',api)
    files=h.files('test/model');assert h.files('test/model')==files and len(calls)==1
    f=files[0];assert f['revision']=='a'*40 and f['sha256']=='b'*64
    assert 'chat_template' not in f['metadata']['gguf']


def test_phone_probe_does_not_start_client_and_cache_is_device_specific(tmp_path,monkeypatch):
    import jiezhi.recommendations as r
    monkeypatch.setattr(r,'DATA',tmp_path);calls=[]
    def adb(*args,**kw):
        calls.append(args)
        return 'Xiaomi\n15 Ultra\nSM8750\nMemTotal: 16000000 kB\nMemAvailable: 4000000 kB\n/dev/dm-1 500000000 100000000 400000000 20% /data\n'
    monkeypatch.setattr(r,'adb',adb)
    p=phone_profile('one');assert p['ram_gib']>15 and not p['cached']
    assert all('am start' not in ' '.join(args) for args in calls)
    def fail(*args,**kw):raise RuntimeError('Disconnected')
    monkeypatch.setattr(r,'adb',fail)
    assert phone_profile('one')['cached']
    assert phone_profile('two')=={}


def test_gui_category_ranking_and_selection(qtbot,tmp_path,monkeypatch):
    import jiezhi.gui as gui
    import jiezhi.hub_view as view
    import jiezhi.hub as hub
    monkeypatch.setattr(gui,'DATA',tmp_path);monkeypatch.setattr(view,'DATA',tmp_path);monkeypatch.setattr(hub,'DATA',tmp_path)
    monkeypatch.setattr(gui.Window,'start_scan',lambda s:None);monkeypatch.setattr(hub.Hub,'restore',lambda s:{})
    monkeypatch.setattr(view,'phone_profile',lambda serial:PHONE)
    repos=[{'id':'test/Qwen3-0.6B-GGUF','siblings':[{'rfilename':'Qwen3-0.6B-Q4_0.gguf'}]}]
    categories=[]
    def discover(self,category):categories.append(category);return repos
    monkeypatch.setattr(hub.Hub,'discover',discover)
    files=[model('Qwen3-0.6B-Q4_0.gguf',.36),model('Qwen3-0.6B-Q8_0.gguf',.7)]
    monkeypatch.setattr(hub.Hub,'files',lambda s,r:files)
    w=gui.Window();qtbot.addWidget(w);w.show();w.nav.setCurrentRow(4)
    qtbot.waitUntil(lambda:len(w.hub_file_data)==2 and not w.workers,timeout=5000)
    assert 'Suitability' in w.hub_files.item(0).toolTip()
    w.hub_files.setCurrentRow(1);chosen=w.hub_files.currentItem().data(view.Qt.ItemDataRole.UserRole)
    w.hub_context.setCurrentIndex(2)
    assert w.hub_files.currentItem().data(view.Qt.ItemDataRole.UserRole)==chosen
    w.hub_category.setCurrentIndex(w.hub_category.findData('fast'))
    qtbot.waitUntil(lambda:'fast' in categories and not w.workers and len(w.hub_file_data)==2,timeout=5000)
    downloaded=[];transferred=[]
    path=tmp_path/'chosen.gguf'
    monkeypatch.setattr(w.hub,'download',lambda file,*args:downloaded.append(file) or path)
    monkeypatch.setattr(w,'transfer_model_path',transferred.append)
    chosen=w.hub_files.currentItem().data(view.Qt.ItemDataRole.UserRole)
    w.client.port=1;w.telemetry_panel.timer.stop()
    w.hub_download(True)
    qtbot.waitUntil(lambda:bool(transferred) and not w.workers,timeout=5000)
    assert downloaded==[chosen] and transferred==[path]
    w.client.port=0
    assert w.telemetry_panel.isVisible()
    w.hub_search_timer.stop();w.close()
