"""Typed, acyclic phone workflows. Graph data never becomes shell commands."""
import copy
import threading
import uuid
import math
from pathlib import Path
from .client import save_json

KINDS={'prompt':'Prompt','llm':'Language model','image':'Image generation','video':'Video generation','output':'Output'}

def node(kind,x=0,y=0):
    if kind not in KINDS:raise ValueError('Unknown node type')
    return {'id':uuid.uuid4().hex,'kind':kind,'title':KINDS[kind],'x':x,'y':y,'params':{
        'prompt':'{{input}}' if kind!='prompt' else 'Describe a quiet garden at sunrise.',
        'model_id':'','context':4096,'max_tokens':256,'backend':'npu',
        'width':1024 if kind=='video' else 512,'height':640 if kind=='video' else 512,'steps':20,'seed':42,'cfg':7.0,'frames':49,'fps':24,
        'negative':'','vae_id':'','encoder_id':'','vision_id':'','image_conditioned':False,'strength':0.65}}

def validate(graph):
    if not isinstance(graph,dict):raise ValueError('Invalid workflow document')
    if graph.get('schema')!=1:raise ValueError('Unsupported workflow version')
    nodes=graph.get('nodes',[]);edges=graph.get('edges',[])
    if not 1<=len(nodes)<=40 or len(edges)>100:raise ValueError('Use 1–40 nodes and at most 100 connections.')
    if not isinstance(nodes,list) or not isinstance(edges,list):raise ValueError('Invalid workflow collections')
    for n in nodes:
        if not isinstance(n,dict) or not isinstance(n.get('id'),str) or not 1<=len(n['id'])<=64:raise ValueError('Invalid node ID')
        if not isinstance(n.get('title'),str) or len(n['title'])>160:raise ValueError('Node names must be at most 160 characters')
        for key in ['x','y']:
            value=n.get(key,0)
            if not isinstance(value,(int,float)) or not math.isfinite(value) or abs(value)>100000:raise ValueError('Invalid node position')
    index={n['id']:n for n in nodes}
    if len(index)!=len(nodes):raise ValueError('Duplicate node IDs')
    for n in nodes:
        if n['kind'] not in KINDS or not isinstance(n.get('params'),dict):raise ValueError('Invalid node')
        p=n['params']
        for key in ['prompt','negative','model_id','vae_id','encoder_id','vision_id','backend']:
            if not isinstance(p.get(key,''),str) or len(p.get(key,''))>16000:raise ValueError('Invalid node text parameter')
        if n['kind']=='llm':
            if p.get('backend','npu') not in {'npu','cpu'}:raise ValueError('Choose phone NPU or CPU for text models')
            for key,lo,hi in [('context',512,8192),('max_tokens',1,2048)]:
                if type(p.get(key)) is not int or not lo<=p[key]<=hi:raise ValueError(f'Invalid {key}: use {lo}–{hi}')
    seen=set();incoming={key:[] for key in index};outgoing={key:[] for key in index}
    for edge in edges:
        if not isinstance(edge,list) or len(edge)!=2:raise ValueError('Invalid connection')
        a,b=edge
        if not isinstance(a,str) or not isinstance(b,str):raise ValueError('Invalid connection IDs')
        if a not in index or b not in index or a==b or (a,b) in seen:raise ValueError('Invalid or duplicate connection')
        if index[a]['kind']=='output' or index[b]['kind']=='prompt':raise ValueError('Prompt is a source; Output is a destination.')
        if index[a]['kind'] in {'image','video'} and index[b]['kind'] not in {'image','video','output'}:raise ValueError('Media cannot feed a text-only model. Use a text branch.')
        if index[a]['kind']=='video' and index[b]['kind']!='output':raise ValueError('Video outputs can feed Output nodes.')
        seen.add((a,b));incoming[b].append(a);outgoing[a].append(b)
    counts={key:len(value) for key,value in incoming.items()};ready=[key for key in index if counts[key]==0];order=[]
    while ready:
        a=ready.pop(0);order.append(a)
        for b in outgoing[a]:
            counts[b]-=1
            if counts[b]==0:ready.append(b)
    if len(order)!=len(nodes):raise ValueError('This connection creates a cycle. Flows must move forward.')
    return index,incoming,order

class WorkflowRunner:
    def __init__(self,client,media,output_dir,emit=lambda e:None,cancelled=None):
        self.client=client;self.media=media;self.output_dir=Path(output_dir);self.emit=emit;self.cancelled=cancelled or threading.Event()
    def check(self):
        if self.cancelled.is_set():raise RuntimeError('Workflow stopped. Completed outputs were kept.')
    def run(self,graph):
        graph=copy.deepcopy(graph);index,incoming,order=validate(graph)
        # Validate every backend before changing model state or starting a node.
        for n in index.values():
            p=n['params']
            image_inputs=[key for key in incoming[n['id']] if index[key]['kind']=='image']
            if len(image_inputs)>1:raise ValueError('A media node accepts one image input. Use separate branches for multiple images.')
            if n['kind']=='video' and image_inputs and not p.get('image_conditioned'):raise ValueError('For an image-to-video connection, choose Image → video and compatible I2V/VACE weights. The Wan starter is text-to-video.')
            if n['kind']=='video' and p.get('image_conditioned') and not image_inputs:raise ValueError('Connect an image node to this image-to-video node.')
            if n['kind'] in {'llm','image','video'} and not p.get('model_id'):raise ValueError(f"Choose a model for {n['title']}.")
            if n['kind'] in {'image','video'}:self.media.validate_node(n)
        if any(n['kind']=='llm' for n in index.values()):
            available={m['id'] for m in self.client.status().get('models',[])}
            for n in index.values():
                if n['kind']=='llm' and n['params']['model_id'] not in available:raise ValueError(f"The model for {n['title']} is missing from the phone.")
        results={};self.output_dir.mkdir(parents=True,exist_ok=True)
        for key in order:
            self.check();n=index[key];p=n['params'];self.emit({'node':key,'state':'running','text':n['title']})
            inputs=[results[a] for a in incoming[key]];text='\n\n'.join(i.get('text','') for i in inputs if i.get('text'))
            prompt=p.get('prompt','').replace('{{input}}',text)
            if n['kind']=='prompt':result={'type':'text','text':prompt}
            elif n['kind']=='llm':
                self.client.load(p['model_id'],p.get('backend','npu'),int(p.get('context',4096)));self.check();tokens=[]
                def event(e):
                    if e['type']=='token':tokens.append(e['text']);self.emit({'node':key,'state':'streaming','text':''.join(tokens)})
                self.client.chat([{'role':'user','content':prompt}],event,max_tokens=int(p.get('max_tokens',256)))
                self.check();result={'type':'text','text':''.join(tokens)}
            elif n['kind'] in {'image','video'}:
                media_inputs=[i for i in inputs if i.get('type')=='image']
                result=self.media.generate(n,prompt,media_inputs,self.output_dir,self.cancelled,lambda msg:self.emit({'node':key,'state':'running','text':msg}))
            else:result={'type':'output','text':text,'items':inputs}
            results[key]=result;save_json(self.output_dir/'results.json',{'graph':graph,'results':results})
            self.emit({'node':key,'state':'complete','text':result.get('text') or result.get('path','Output ready'),'result':result})
        return results
