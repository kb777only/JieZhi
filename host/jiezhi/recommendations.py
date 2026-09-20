"""Explainable model/phone fit heuristics. No inference or model downloads."""
from __future__ import annotations
import math
import re
import time
from .client import DATA, adb, devices, read_json, save_json

GIB=1024**3
CATEGORIES={'chat':'Everyday chat','code':'Coding','reason':'Reasoning','docs':'Documents','fast':'Fast replies'}
DISCOVERY={
 'chat':['Qwen3-1.7B','Qwen3-4B','Llama-3.2-3B'],
 'code':['Qwen2.5-Coder-1.5B','Qwen2.5-Coder-3B','Qwen3-4B'],
 'reason':['Qwen3-4B','DeepSeek-R1-Distill-Qwen-1.5B','Qwen3-1.7B'],
 'docs':['Qwen3-4B','Qwen3-1.7B','Llama-3.2-3B'],
 'fast':['Qwen3-0.6B','Qwen3-1.7B','SmolLM2-1.7B'],
}
PHONE_SCRIPT='''getprop ro.product.manufacturer
getprop ro.product.model
getprop ro.soc.model
head -n 8 /proc/meminfo
df -k /data
'''


def phone_profile(serial=''):
    """Read hardware through ADB without starting the Android client or a model."""
    path=DATA/'recommendation-phone.json'
    previous=read_json(path,{})
    try:
        if not serial:
            found=[d['serial'] for d in devices() if d['state']=='device']
            if len(found)!=1:return {**previous,'cached':True} if previous else {}
            serial=found[0]
        lines=adb('shell',PHONE_SCRIPT,serial=serial,timeout=5).splitlines()
        memory=dict(re.findall(r'(MemTotal|MemAvailable):\s+(\d+) kB','\n'.join(lines)))
        if len(lines)<3 or 'MemTotal' not in memory:raise ValueError('Hardware unavailable')
        disk=next((line.split() for line in reversed(lines) if len(line.split())>=6 and line.split()[-1].startswith('/data')),[])
        profile={'serial':serial,'phone':' '.join(lines[:2]),'soc':lines[2].strip(),
                 'ram_gib':int(memory['MemTotal'])*1024/GIB,
                 'available_gib':int(memory.get('MemAvailable',0))*1024/GIB,
                 'storage_gib':int(disk[3])*1024/GIB if len(disk)>=6 and disk[3].isdigit() else None,
                 'sampled_at':time.time(),'cached':False}
        save_json(path,profile);return profile
    except Exception:
        # Never reuse a different device's calibration after explicit selection.
        return {**previous,'cached':True} if previous and (not serial or previous.get('serial')==serial) else {}


def parameters(name, metadata):
    # Expert models need ALL weights in RAM, not just active parameter count.
    total=(metadata.get('gguf') or {}).get('total') or (metadata.get('safetensors') or {}).get('total')
    if isinstance(total,(int,float)) and math.isfinite(total) and total>0:return total/1e9
    match=re.search(r'(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)b\b',name,re.I)
    if match:return float(match[1])*float(match[2])
    matches=re.findall(r'(?<![\w.])(\d+(?:\.\d+)?)[bB](?!\w)',name)
    return float(matches[0]) if matches else None


def quantization(name):
    match=re.search(r'(?<![A-Z0-9])(?:IQ\d_[A-Z0-9_]+|Q\d(?:_[A-Z0-9]+)*|BF16|F16|F32)(?=\.|-|$)',name.upper())
    return match[0] if match else None


def evaluate(model, phone, category='chat', context=4096):
    name=model.get('name') or model.get('id') or model.get('modelId','Unknown model')
    metadata=model.get('metadata',model); text=(name+' '+' '.join(metadata.get('tags',[]))).lower()
    p=parameters(name,metadata);quant=quantization(name)
    preview='name' not in model
    if preview:
        variants=[s.get('rfilename','') for s in metadata.get('siblings',[])]
        quant='Q4_0' if any(quantization(v)=='Q4_0' for v in variants) else 'Q4_K_M' if any(quantization(v)=='Q4_K_M' for v in variants) else None
    arch=(metadata.get('gguf') or {}).get('architecture') or (metadata.get('config') or {}).get('model_type','')
    hybrid=any(t in (text+' '+arch) for t in ['moe','mixtral','qwen3.5','qwen3_5','mamba','jamba']) or bool(re.search(r'\d+x\d+b|\d+b-a\d+b',text))
    dense=not hybrid and (any(t in text for t in ['qwen3-','qwen2.5-','llama-3','llama3','smollm2']) or arch in {'qwen3','qwen2','llama'})
    qwen3=dense and ('qwen3-' in text or arch=='qwen3')
    size=model.get('size',0)/GIB
    if not size and p and quant:
        bits=16 if quant in {'F16','BF16'} else 32 if quant=='F32' else int(re.search(r'\d',quant)[0])+.6
        size=p*1e9*bits/8/GIB
    memory=None
    if size and p:
        memory=(size*1.05+.6+p*.08*context/2048,size*1.25+1+p*.25*context/2048)
    ram=phone.get('ram_gib');budget=max(0,ram-max(3,ram*.25)) if ram else None
    supported='8750' in phone.get('soc','')
    fit='RAM unknown';fit_points=8
    if memory and budget is not None:
        if memory[0]>budget:fit='Too large';fit_points=0
        elif memory[1]>budget:fit='Tight RAM';fit_points=18
        else:fit='Fits RAM estimate';fit_points=40
    blocked=bool(model.get('split')) or bool(re.search(r'mmproj|projector',name,re.I))
    if preview:
        weights=[v for v in variants if v.lower().endswith('.gguf') and not re.search(r'mmproj|projector',v,re.I)]
        if variants and (not weights or all(re.search(r'-\d{5}-of-\d{5}\.gguf$',v,re.I) for v in weights)):blocked=True
    pipeline=metadata.get('pipeline_tag','')
    if pipeline and pipeline not in {'text-generation','image-text-to-text'}:blocked=True
    storage=phone.get('storage_gib')
    if size and storage is not None and size+.25>storage:fit='Storage too small';blocked=True
    if metadata.get('disabled'):blocked=True
    if blocked:
        if fit!='Storage too small':fit='Unsupported file/task'
        fit_points=0
    if not supported:fit='Phone not calibrated' if phone else 'Connect a phone';fit_points=0
    category_points=10
    if p:
        if category=='fast':category_points=max(0,30-p*8)
        elif category=='chat':category_points=25 if 1.3<=p<=4.5 else 15 if p<9 else 8
        elif category=='code':category_points=30 if any(t in text for t in ['coder','coding','code-']) else 8
        elif category=='reason':category_points=(30 if p>=3 else 18) if any(t in text for t in ['qwen3','reason','deepseek-r1','qwq']) else 8
        elif category=='docs':category_points=(30 if p>=3 else 22) if p>=1.5 and dense else 10
    max_context=(metadata.get('gguf') or {}).get('context_length')
    if isinstance(max_context,(int,float)) and 0<max_context<context:fit='Context exceeds metadata';blocked=True
    speed=None;confidence='uncalibrated'
    if p and p>0 and supported and dense and quant and not blocked and fit!='Too large':
        # Empirical SM8750/Qwen3 Q4_0 references: 0.6B ~69, 1.7B ~34 tok/s.
        # Other dense families/quants get deliberately broad extrapolation bands.
        center=min(150,34*(1.7/p)**.70)
        if qwen3 and quant=='Q4_0':lo,hi=.70,1.30;confidence='reference-based estimate'
        else:
            lo,hi=.15,.90;confidence='low-confidence estimate'
            bits=16 if quant in {'F16','BF16'} else 32 if quant=='F32' else int(re.search(r'\d',quant)[0])+.6
            center*=min(1,(4.6/bits)**.65)
            if quant.startswith('IQ'):center*=.75
        if context>4096:lo*=.75;hi*=.9
        if fit=='Tight RAM':lo*=.5;hi*=.8
        speed=(max(1,round(center*lo)),max(2,round(center*hi)))
    runtime_points=(18 if quant=='Q4_0' else 13 if quant and quant.startswith('Q4') else 4 if quant in {'F16','BF16','F32'} else 9) if dense else 2
    speed_points=min(10,(sum(speed)/2)/6) if speed else 0
    score=round(min(99,fit_points+category_points+runtime_points+speed_points))
    if blocked or fit=='Too large':score=min(score,10)
    if not supported or fit=='RAM unknown':score=min(score,35)
    if hybrid or not dense:score=min(score,55)
    recommendation=score>=72 and fit=='Fits RAM estimate' and not blocked and dense
    speed_text=f'Est. {speed[0]}–{speed[1]} tok/s' if speed else 'tok/s uncalibrated'
    ram_text=f'Est. RAM {memory[0]:.1f}–{memory[1]:.1f} GiB' if memory else 'RAM estimate unavailable'
    reason={ 'chat':'Balanced size for chat','code':'Coding signals in model metadata' if category_points==30 else 'No coding specialization found',
             'reason':'Reasoning signals in metadata; larger fitting models favored' if category_points>=18 else 'No reasoning specialization found',
             'docs':'Text reference workloads','fast':'Smaller models favored for responsiveness'}[category]
    details=[f'Suitability {score}/100 for {CATEGORIES[category]}: {reason}. This is a heuristic fit score, not a quality benchmark.',
             f'{fit}. RAM budget reserves max(3 GiB, 25%) for Android; estimates assume the previous model is unloaded.',
             f'{ram_text} at {context} context tokens; KV cache is a conservative parameter-based approximation.',
             f'{speed_text}: {confidence}. Generation/decode only, excludes prefill and USB transfer. Thermal throttling, prompt length and runtime support change results.',
             'Reference: Xiaomi 15 Ultra / SM8750, GenieX 0.7.0, Qwen3 0.6B and 1.7B Q4_0; see docs/validation.md. Other dense models are extrapolations, not benchmarks.',
             'Repository previews assume the named quantization; choose a file for its actual size. No promise of architecture/quantization support.']
    if metadata.get('gated'):details.append('Gated repository: Hugging Face access approval may be needed.')
    return {'score':score,'recommended':recommendation,'fit':fit,'speed':speed,'memory':memory,'quant':quant,'parameters':p,
            'lines':[f"{'Recommended · ' if recommendation else ''}Suitability {score}/100 · {fit}",
                     f'{speed_text} · {quant or "Quant unknown"}'+(' preview' if preview else '')+(' · low confidence' if confidence=='low-confidence estimate' else ''),ram_text+f' · {context//1024}K context'],
            'details':'\n\n'.join(details),'blocked':blocked,'confidence':confidence}


def ranked(models,phone,category='chat',context=4096):
    results=[(model,evaluate(model,phone,category,context)) for model in models]
    return sorted(results,key=lambda pair:(-pair[1]['score'],-pair[0].get('downloads',0),(pair[0].get('name') or pair[0].get('id','')).lower()))
