"""Authenticated USB media transport; all inference stays on the Android phone."""
import hashlib
import time
import math
from pathlib import Path
from .client import save_json

class MediaClient:
    def __init__(self,client):self.client=client
    def models(self):return self.client.request('GET','/media').json()['models']
    def validate_node(self,node):
        p=node['params'];backend=p.get('backend','cpu');kind=node['kind']
        if backend not in {'cpu','npu'}:raise ValueError('Choose phone NPU or CPU for media.')
        for key,default,lo,hi in [('seed',42,0,2147483647),('fps',24,1,30),('steps',20,1,50),('width',512,128,1024),('height',512,128,1024),('frames',49,5,81)]:
            value=p.get(key,default)
            if type(value) is not int or not lo<=value<=hi:raise ValueError(f'{key} must be an integer between {lo} and {hi}.')
        cfg=p.get('cfg',7)
        if not isinstance(cfg,(int,float)) or not math.isfinite(cfg) or not 1<=cfg<=20:raise ValueError('Guidance must be between 1 and 20.')
        if backend=='npu':
            expected=(512,512) if kind=='image' else (1024,640)
            if (p['width'],p['height'])!=expected:raise ValueError(f'This NPU pipeline uses {expected[0]}×{expected[1]}.')
            if kind=='video' and p['frames']!=49:raise ValueError('Neodragon uses its compiled 49-frame schedule.')
        else:
            if any(p[key]%64 for key in ['width','height']):raise ValueError('Media dimensions must be multiples of 64.')
            if kind=='video':
                if not p.get('vae_id') or not p.get('encoder_id'):raise ValueError('CPU video needs a compatible VAE and UMT5 text encoder.')
                if p['frames']%4!=1:raise ValueError('Video frame count must be 5, 9, 13, …, 81.')
                if max(p['width'],p['height'])>512:raise ValueError('CPU video is limited to 512 pixels per dimension.')
        info=self.client.request('GET','/media').json()
        if not info.get('available'):raise ValueError('Install the updated Android client for media generation.')
        models={m['id']:m for m in info['models']};selected=models.get(p.get('model_id'),{})
        if backend=='npu':
            if backend not in info.get('backends',[]):raise ValueError('Install the NPU media-enabled Android client.')
            if selected.get('format')!=('qnn' if kind=='image' else 'neodragon'):raise ValueError('Select the matching QNN image package or Neodragon video bundle. GGUF cannot be used on this NPU path.')
        elif selected.get('format') in {'qnn','neodragon'}:raise ValueError('This model package needs the NPU backend.')
        if kind=='video' and p.get('image_conditioned') and 't2v' in selected.get('name','').lower() and 'ti2v' not in selected.get('name','').lower():raise ValueError('Import compatible I2V/VACE weights for an image connection; this model is text-to-video.')
        keys=['model_id'] if backend=='npu' else ['model_id','vae_id','encoder_id','vision_id']
        for key in keys:
            if p.get(key) and p[key] not in models:raise ValueError(f'{key} is missing from the phone media library.')
    def upload(self,path,progress=lambda *_:None,cancelled=None,format_hint=None):
        path=Path(path);fmt=format_hint or ('qnn' if path.suffix.lower()=='.zip' else path.suffix.lower().lstrip('.'))
        if fmt not in {'gguf','safetensors','qnn','data'}:raise ValueError('Use GGUF, safetensors or a converted QNN ZIP package.')
        size=path.stat().st_size
        if not 16<=size<=16*1024**3:raise ValueError('Media weight files must be 16 bytes–16 GiB.')
        digest=hashlib.sha256()
        def check():
            if cancelled and cancelled.is_set():raise RuntimeError('Media transfer stopped. Import again to resume.')
        with path.open('rb') as stream:
            while block:=stream.read(4*1024**2):check();digest.update(block)
        key=digest.hexdigest();status=self.client.request('POST','/media/uploads',json={'id':key,'name':path.name,'size':size,'format':fmt}).json()
        if not status['complete']:
            offset=status['offset']
            if not 0<=offset<=size:raise RuntimeError('Invalid phone upload offset')
            with path.open('rb') as stream:
                stream.seek(offset)
                while block:=stream.read(4*1024**2):
                    check()
                    response=self.client.session.put(self.client.url('/media/uploads/'+key),headers={**self.client.headers(),'X-Offset':str(offset),'Content-Type':'application/octet-stream'},data=block,timeout=(5,90))
                    if not response.ok:raise RuntimeError(response.json().get('error','Media transfer failed'))
                    offset=response.json()['offset'];progress(offset*100//size,'Sending media weights to phone')
            self.client.request('POST','/media/commit',json={'id':key},timeout=(5,300))
        return self.models()
    def import_image(self,data):
        if not 8<=len(data)<=16*1024**2:raise ValueError('Input image must be at most 16 MiB.')
        return self.client.request('POST','/media/images',data=data).json()
    def cancel(self):return self.client.request('POST','/media/cancel',json={},timeout=(3,10))
    def generate(self,node,prompt,inputs,output_dir,cancelled,progress):
        params={**node['params'],'kind':node['kind'],'prompt':prompt}
        if not prompt.strip():raise ValueError('Connect a nonempty prompt or enter one in the node settings.')
        if len(prompt)>16000:raise ValueError('Media prompts are limited to 16,000 characters.')
        if inputs:params['init_result']=inputs[0]['phone_result']
        job=self.client.request('POST','/media/generate',json=params).json();job_id=job['id']
        while True:
            if cancelled.wait(1):self.cancel();raise RuntimeError('Workflow stopped; completed outputs were kept.')
            current=self.client.request('GET','/media/job',timeout=(5,10)).json()
            if current.get('id')!=job_id:raise RuntimeError('Phone media job changed unexpectedly.')
            progress(current.get('log','Generating on the phone…'))
            if current['state']=='complete':break
            if current['state'] in {'failed','cancelled'}:raise RuntimeError(current.get('error') or current.get('log') or current['state'])
        name=current['result']
        if Path(name).name!=name or Path(name).suffix not in {'.png','.avi','.mp4'}:raise RuntimeError('Invalid result filename')
        path=Path(output_dir)/name;partial=path.with_suffix(path.suffix+'.partial');digest=hashlib.sha256();size=0
        with self.client.request('GET','/media/results/'+name,stream=True) as response,partial.open('wb') as stream:
            for block in response.iter_content(1024**2):
                if cancelled.is_set():partial.unlink(missing_ok=True);raise RuntimeError('Stopped while retrieving output')
                size+=len(block)
                if size>current['size']:raise RuntimeError('Output exceeded expected size')
                digest.update(block);stream.write(block)
        if size!=current['size'] or digest.hexdigest()!=current['sha256']:partial.unlink(missing_ok=True);raise RuntimeError('Media output checksum failed')
        partial.replace(path)
        return {'type':node['kind'],'path':str(path),'phone_result':name,'backend':'phone-'+params.get('backend','cpu'),'prompt':prompt}
