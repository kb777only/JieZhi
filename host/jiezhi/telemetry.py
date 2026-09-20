"""Phone telemetry with explicit sensor provenance and no fabricated utilization."""
from __future__ import annotations
import math
import re
import time
import requests
from .client import adb

# All shell text is constant. No paths or commands originate from model/user content.
HARDWARE_SCRIPT = r'''
echo JZ_CPU
head -n 1 /proc/stat 2>/dev/null
echo JZ_MEM
head -n 8 /proc/meminfo 2>/dev/null
echo JZ_GPU
if [ -r /sys/class/kgsl/kgsl-3d0/gpubusy ]; then cat /sys/class/kgsl/kgsl-3d0/gpubusy; else echo unavailable; fi
echo JZ_THERMAL
dumpsys thermalservice 2>/dev/null | sed -n '/Current temperatures from HAL:/,/Current cooling devices from HAL:/p'
echo JZ_END
'''


def number(value, low=None, high=None):
    if isinstance(value, bool): return None
    try: result=float(value)
    except (TypeError,ValueError): return None
    if not math.isfinite(result) or (low is not None and result<low) or (high is not None and result>high):return None
    return result


def parse_hardware(text):
    parts={}
    for match in re.finditer(r'^JZ_(CPU|MEM|GPU|THERMAL)\n(.*?)(?=^JZ_|\Z)',text,re.M|re.S):parts[match[1]]=match[2].strip()
    cpu=None
    line=parts.get('CPU','').splitlines()
    if line and re.fullmatch(r'cpu(?:\s+\d+){4,}',line[0]):
        values=list(map(int,line[0].split()[1:]))[:8]
        cpu=(sum(values),values[3]+(values[4] if len(values)>4 else 0))
    mem={key:int(value)*1024 for key,value in re.findall(r'^(MemTotal|MemAvailable):\s+(\d+) kB',parts.get('MEM',''),re.M)}
    gpu=None
    match=re.fullmatch(r'\s*(\d+)\s+(\d+)\s*',parts.get('GPU',''))
    if match and int(match[2])>0 and int(match[1])<=int(match[2]):gpu=100*int(match[1])/int(match[2])
    thermal=parts.get('THERMAL','')
    # Cached HAL values can be hours old. Only use the explicitly current section.
    current=thermal.split('Current temperatures from HAL:',1)[1].split('Current cooling devices',1)[0] if 'Current temperatures from HAL:' in thermal else ''
    sensors=[]
    for value,kind,name in re.findall(r'Temperature\{mValue=([^,]+), mType=(\d+), mName=([^,]+),',current):
        value=number(value,-40,150);kind=int(kind)
        # Types 6/7/8 are electrical/BCL readings, despite appearing in Temperature objects.
        if value is not None and kind in {0,1,2,3,9}:sensors.append({'name':name,'type':kind,'c':value})
    cpu_t=[s['c'] for s in sensors if s['type']==0]
    return {'cpu_counters':cpu,'memory_total_bytes':mem.get('MemTotal'),'memory_available_bytes':mem.get('MemAvailable'),
            'gpu_percent':gpu,'soc_c':max(cpu_t) if cpu_t else None,'sensors':sensors}


class Collector:
    def __init__(self):
        self.target=None;self.previous_cpu=None;self.hardware={};self.hardware_at=0.;self.hardware_error='';self.session=requests.Session();self.session.trust_env=False
    def sample(self, serial, port, token):
        target=(serial,port,token)
        if self.target!=target:
            self.target=target;self.previous_cpu=None;self.hardware={};self.hardware_at=0.;self.hardware_error=''
        now=time.monotonic();app={};api_error=''
        try:
            response=self.session.get(f'http://127.0.0.1:{port}/v1/telemetry',headers={'Authorization':f'Bearer {token}'},timeout=(1,2))
            if response.status_code==404:api_error='Update the Android client for live token and battery readings.'
            elif response.status_code==401:api_error='Pair the Android client again.'
            else:response.raise_for_status();app=response.json()
        except (requests.RequestException,ValueError):api_error='Phone telemetry connection lost.'
        if now-self.hardware_at>=2:
            try:
                hardware=parse_hardware(adb('shell',HARDWARE_SCRIPT,serial=serial,timeout=4))
                counters=hardware.pop('cpu_counters');load=None
                if counters and self.previous_cpu:
                    total=counters[0]-self.previous_cpu[0];idle=counters[1]-self.previous_cpu[1]
                    if total>0 and 0<=idle<=total:load=100*(total-idle)/total
                self.previous_cpu=counters;hardware['cpu_percent']=load
                self.hardware=hardware;self.hardware_at=time.monotonic();self.hardware_error=''
            except Exception:
                self.previous_cpu=None;self.hardware={};self.hardware_at=time.monotonic();self.hardware_error='ADB hardware sensors could not be read.'
        values={
            'tokens':number(app.get('stream_rate'),0),
            'battery':number(app.get('battery_percent'),0,100),
            'battery_temp':number(app.get('battery_c'),-40,100),
            'soc_temp':self.hardware.get('soc_c'),
            'cpu':self.hardware.get('cpu_percent'),
            'gpu':self.hardware.get('gpu_percent'),
            'npu':None,
        }
        total=number(self.hardware.get('memory_total_bytes') or app.get('memory_total_bytes'),1)
        available_raw=self.hardware.get('memory_available_bytes')
        available=number(app.get('memory_available_bytes') if available_raw is None else available_raw,0)
        used=total-available if total is not None and available is not None and available<=total else None
        values['memory']=used/1024**3 if used is not None else None
        reasons={
            'tokens':api_error or 'Two-second SDK token-callback rate. Approximate; final runtime tokens/s is shown separately.',
            'battery':api_error or ('USB/power connected' if app.get('plugged') else 'On battery'),
            'battery_temp':api_error or 'Android battery temperature, °C.',
            'soc_temp':'Hottest current CPU thermal-HAL sensor, not the BCL percentage sensor named socd.',
            'cpu':'Whole-phone CPU busy time from successive /proc/stat samples, across all cores.',
            'gpu':'KGSL busy / total interval.' if values['gpu'] is not None else 'Android blocks the KGSL GPU busy counter on this phone. Temperature is not utilization.',
            'npu':'No accessible NPU utilization counter on this phone. Inference activity and thermal status are not hardware load percentages.',
            'memory':'Whole-phone RAM: total minus OS-available memory. Includes the OS and other apps.',
        }
        if self.hardware_error:
            for key in ['soc_temp','cpu','gpu']:reasons[key]=self.hardware_error
        if values['soc_temp'] is None and not self.hardware_error:reasons['soc_temp']='Current CPU/SoC temperature sensors are unavailable.'
        if values['cpu'] is None and not self.hardware_error:reasons['cpu']='Waiting for two CPU counter samples, or /proc/stat is unavailable.'
        return {'at':time.monotonic(),'serial':serial,'values':values,'reasons':reasons,'sensors':self.hardware.get('sensors',[]),
                'app':app,'memory_total_gib':total/1024**3 if total else None,'hardware_age':time.monotonic()-self.hardware_at,
                'connected':bool(app),'notice':api_error or self.hardware_error}
