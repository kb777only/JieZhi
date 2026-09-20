"""Local project workspaces: linked folders, reference documents, and chats."""
from pathlib import Path
import os
import re
import uuid
from .client import DATA, save_json, read_json
from .attachments import extract, TEXT_EXTENSIONS, excerpt
from .pc_tools import sensitive, SKIP_DIRS, redact

SUPPORTED = TEXT_EXTENSIONS | {'.pdf','.xlsx','.xlsm','.xls','.ods'}


class Projects:
    def __init__(self, data=None): self.data=data or DATA/'projects'
    def all(self):
        return sorted((read_json(p,{}) for p in self.data.glob('*.json')), key=lambda p:p.get('name','').lower())
    def save(self, project):
        if not re.fullmatch(r'[a-f0-9]{32}', project['id']): raise ValueError('Invalid project ID.')
        save_json(self.data/f"{project['id']}.json",project)
    def create(self,name):
        name=name.strip()
        if not name or len(name)>80: raise ValueError('Use a project name of 1–80 characters.')
        project={'id':uuid.uuid4().hex,'name':name,'instructions':'','folders':[],'documents':[]}
        self.save(project); return project
    def remove(self,project):
        # Metadata only; linked folders and chats are never deleted here.
        (self.data/f"{project['id']}.json").unlink(missing_ok=True)
    def index(self,project):
        result=[]; visited=0
        for base in project.get('folders',[]):
            root=Path(base)
            if not root.is_dir() or root.is_symlink() or sensitive(root): continue
            for folder,dirs,files in os.walk(root,followlinks=False):
                dirs[:]=sorted(d for d in dirs if d not in SKIP_DIRS and not sensitive(Path(folder)/d) and not (Path(folder)/d).is_symlink())
                for name in sorted(files):
                    visited+=1
                    path=Path(folder)/name
                    if visited>10000 or len(result)>=1000: return result
                    if path.is_symlink() or sensitive(path) or path.suffix.lower() not in SUPPORTED: continue
                    try:
                        if path.stat().st_nlink!=1 or path.stat().st_size>20*1024**2: continue
                    except OSError: continue
                    result.append({'path':str(path),'name':str(path.relative_to(root)),'root':str(root)})
        return result
    def references(self,project,query):
        terms=set(re.findall(r'\w{2,}',query.lower()))
        docs=[dict(d) for d in project.get('documents',[])]
        entries=self.index(project)
        entries.sort(key=lambda f:-sum(t in f['name'].lower() for t in terms))
        # Bounded local lookup. Explicit project documents always participate.
        for entry in entries[:40]:
            path=Path(entry['path'])
            try:
                # Avoid expensive workbook/PDF extraction unless the name matches.
                if path.suffix.lower() in {'.pdf','.xlsx','.xlsm','.xls','.ods'} and not any(t in entry['name'].lower() for t in terms): continue
                doc=extract(path); doc['name']=entry['name']; doc['text']=redact(doc['text']); docs.append(doc)
            except (OSError,ValueError): continue
        docs.sort(key=lambda d:-sum(d['name'].lower().count(t)*4+d['text'].lower().count(t) for t in terms))
        unique={}
        for doc in docs:
            if doc['id'] not in unique: unique[doc['id']]=doc
        return list(unique.values())[:3]
