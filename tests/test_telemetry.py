import time
from jiezhi.telemetry import parse_hardware, Collector
from jiezhi.telemetry_view import TelemetryPanel
from jiezhi.client import Client

SAMPLE='''JZ_CPU
cpu 100 20 30 800 20 10 10 0 50 5
JZ_MEM
MemTotal: 16000000 kB
MemAvailable: 6000000 kB
JZ_GPU
20 100
JZ_THERMAL
Cached temperatures:
 Temperature{mValue=99.3, mType=0, mName=CPU0, mStatus=0}
Current temperatures from HAL:
 Temperature{mValue=48.0, mType=0, mName=CPU0, mStatus=0}
 Temperature{mValue=50.0, mType=0, mName=CPU1, mStatus=0}
 Temperature{mValue=88.0, mType=8, mName=socd, mStatus=0}
 Temperature{mValue=42.0, mType=9, mName=nsp0, mStatus=0}
 Temperature{mValue=NaN, mType=1, mName=GPU0, mStatus=0}
Current cooling devices from HAL:
JZ_END
'''


def test_parse_current_not_cached_temperatures_and_bcl():
    result=parse_hardware(SAMPLE)
    assert result['soc_c']==50
    assert result['gpu_percent']==20
    assert result['cpu_counters']==(990,820) # Guest times must not be counted twice.
    assert result['memory_total_bytes']==16000000*1024
    assert {s['name'] for s in result['sensors']}=={'CPU0','CPU1','nsp0'}


def test_missing_sensors_remain_unknown():
    result=parse_hardware('JZ_GPU\nunavailable\nJZ_END\n')
    assert result['gpu_percent'] is None and result['soc_c'] is None and result['cpu_counters'] is None
    assert parse_hardware(SAMPLE.replace('20 100','101 100'))['gpu_percent'] is None


def test_collector_deltas_failure_and_identity_reset(monkeypatch):
    import jiezhi.telemetry as module
    collector=Collector()
    class Response:
        status_code=200
        def raise_for_status(self):pass
        def json(self):return {'stream_rate':12,'battery_percent':55,'battery_c':37,'generating':True}
    monkeypatch.setattr(collector.session,'get',lambda *a,**kw:Response())
    samples=iter([SAMPLE,SAMPLE.replace('100 20 30 800 20 10 10 0','200 20 30 900 20 10 10 0'),SAMPLE])
    monkeypatch.setattr(module,'adb',lambda *a,**kw:next(samples))
    first=collector.sample('phone',1,'token');assert first['values']['cpu'] is None
    collector.hardware_at=0
    second=collector.sample('phone',1,'token');assert second['values']['cpu']==50 and second['values']['npu'] is None
    assert second['values']['memory']>0
    third=collector.sample('other',2,'token');assert third['values']['cpu'] is None


def test_panel_updates_all_graphs_and_disconnect_gaps(qtbot):
    panel=TelemetryPanel(Client());qtbot.addWidget(panel);panel.timer.stop();panel.resize(1040,140);panel.show()
    result={'at':time.monotonic(),'app':{'generating':True},'values':{k:5.0 for k in panel.cards},'reasons':{k:'Test source' for k in panel.cards},'memory_total_gib':16,'notice':'','sensors':[]}
    result['values']['gpu']=None;result['values']['npu']=None
    panel.receive(result)
    assert panel.cards['tokens'].value.text()=='5.0'
    assert panel.cards['npu'].value.text()=='—'
    panel.unavailable('Disconnected')
    assert all(c.chart.points[-1][1] is None for c in panel.cards.values())
    assert all(c.value.text()=='—' for c in panel.cards.values())
    panel.shutdown()
