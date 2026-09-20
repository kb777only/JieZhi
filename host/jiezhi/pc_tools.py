"""Host-side permissions and tools. Model output is always an untrusted proposal."""
from __future__ import annotations
import configparser
import difflib
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import selectors
import signal
import stat
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass
from .client import DATA, save_json, read_json

MODES = {'inspect': 'Read-only', 'confirm': 'Ask before changes', 'workspace': 'Scoped autonomy'}
SENSITIVE = {'.ssh', '.gnupg', '.aws', '.azure', '.kube', '.pki', '.mozilla', '.git', 'keyrings', 'chromium', 'google-chrome', 'BraveSoftware', 'wallets', 'passwords', 'credentials', 'secrets', 'shadow', 'gshadow', '.codex'}
SKIP_DIRS = {'.venv', 'venv', 'node_modules', '__pycache__', 'build', 'dist', '.cache', '.tools'}


def sensitive(path: Path):
    return any(p.lower() in {s.lower() for s in SENSITIVE} or p.lower().startswith('.env') or p.lower().endswith(('.pem', '.key', '.p12', '.pfx', '.kdbx')) for p in path.parts)


def redact(text):
    text = re.sub(r'\bhf_[A-Za-z0-9]{6,}', '[REDACTED]', text)
    text = re.sub(r'(?i)(bearer\s+)\S+', r'\1[REDACTED]', text)
    return re.sub(r'(?im)((?:password|passwd|api[_-]?key|access[_-]?token|secret)\s*[:=]\s*)[^\s,;]+', r'\1[REDACTED]', text)


def digest(data): return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class Policy:
    mode: str = 'confirm'
    roots: tuple[Path, ...] = ()
    allow_admin: bool = False

    def __post_init__(self):
        if self.mode not in MODES: raise ValueError('Unknown access mode.')
        object.__setattr__(self, 'roots', tuple(Path(p).resolve(strict=True) for p in self.roots))


class Cancelled(Exception): pass
class Denied(Exception): pass


class Tools:
    def __init__(self, policy: Policy, approve=lambda proposal: False, emit=lambda event: None, cancel=None, data=None):
        self.policy = policy; self.approve = approve; self.emit = emit
        self.cancel = cancel or threading.Event(); self.data = data or DATA / 'assistant'
        self.run_id = uuid.uuid4().hex; self.events = []
        self.identities = {p: (p.stat().st_dev, p.stat().st_ino) for p in policy.roots}
        self.read_roots = tuple(p for p in (Path('/usr/share/applications'), Path.home()/'.local/share/applications') if p.is_dir())

    def check_cancel(self):
        if self.cancel.is_set(): raise Cancelled('Stopped by user.')

    def record(self, kind, **details):
        event = {'time': time.time(), 'kind': kind, **details}
        self.events.append(event)
        save_json(self.data/'runs'/f'{self.run_id}.json', {'id': self.run_id, 'mode': self.policy.mode, 'roots': list(map(str,self.policy.roots)), 'events': self.events})
        self.emit(event)

    def path(self, value, write=False):
        path = Path(value).expanduser().absolute()
        if sensitive(path) or path.is_relative_to(self.data.resolve()) or path.is_relative_to(DATA.resolve()):
            raise Denied('Credentials, assistant data and sensitive folders are excluded.')
        roots = self.policy.roots + (() if write else self.read_roots)
        for root in roots:
            try: relative = path.relative_to(root)
            except ValueError: continue
            if '..' in relative.parts: raise Denied('Parent traversal is blocked.')
            if root in self.identities and (root.stat().st_dev, root.stat().st_ino) != self.identities[root]:
                raise Denied('The selected folder changed. Select it again.')
            current = root
            for part in relative.parts:
                current /= part
                if current.is_symlink(): raise Denied('Symlinks are excluded from folder access.')
            if not path.resolve().is_relative_to(root): raise Denied('Path escapes the selected folder.')
            return path, root, relative
        raise Denied('This path is outside selected folders. Add its folder in Assistant access settings.')

    def parent_fd(self, value, write=False):
        path, root, relative = self.path(value,write)
        if not relative.parts: raise Denied('Select a file within the folder.')
        fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for part in relative.parts[:-1]:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd); fd = child
            return fd, relative.name, path
        except BaseException:
            os.close(fd); raise

    def read(self, value, write=False):
        directory, name, path = self.parent_fd(value, write)
        try:
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
            with os.fdopen(fd, 'rb') as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                    raise Denied('Only regular files with a single hard link are allowed.')
                if info.st_size > 65536: raise Denied('Tool reads/edits are limited to 64 KiB text files. Use attachments for larger documents.')
                raw = stream.read(65537)
                if len(raw)>65536: raise Denied('File grew beyond the read limit.')
            raw.decode('utf-8')
            return raw, info
        finally: os.close(directory)

    def process(self, argv, cwd=None, timeout=20, elevated=False):
        self.check_cancel()
        env = {k:v for k,v in os.environ.items() if k in {'HOME','USER','LOGNAME','LANG','DISPLAY','WAYLAND_DISPLAY','XAUTHORITY','XDG_RUNTIME_DIR','DBUS_SESSION_BUS_ADDRESS'}}
        env.update(PATH='/usr/bin:/bin', LC_ALL='C.UTF-8', PAGER='cat', SYSTEMD_PAGER='cat', SYSTEMD_PAGERSECURE='1')
        if elevated: argv = ['/usr/bin/pkexec', *argv]
        elif Path('/usr/bin/setpriv').exists(): argv = ['/usr/bin/setpriv','--no-new-privs','--',*argv]
        process = subprocess.Popen(argv, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, start_new_session=True)
        chunks = bytearray(); deadline = time.monotonic()+timeout; reason = ''
        def terminate():
            try: os.killpg(process.pid,signal.SIGKILL)
            except ProcessLookupError: pass
            except PermissionError:
                raise Denied(f'Administrator process {process.pid} could not be stopped with your user permissions and may still be running. Inspect it through system tools before continuing; no further assistant actions will run.') from None
        selector = selectors.DefaultSelector(); selector.register(process.stdout, selectors.EVENT_READ)
        try:
            while selector.get_map() or process.poll() is None:
                if self.cancel.is_set(): reason='Stopped by user'; break
                if time.monotonic()>deadline: reason='Command timed out'; break
                for key,_ in selector.select(0.1):
                    data = os.read(key.fileobj.fileno(),4096)
                    if not data: selector.unregister(key.fileobj); break
                    chunks.extend(data)
                    if len(chunks)>16000: reason='Output limit reached'; break
                if reason: break
            if reason:
                # Kill the entire process group, including children holding stdout open.
                terminate()
            code=process.wait(timeout=3)
        finally:
            selector.close(); process.stdout.close()
            if process.poll() is None:
                terminate()
                process.wait()
        if self.cancel.is_set(): raise Cancelled('Stopped by user. A command may have partially changed the PC; inspect the action log.')
        return {'exit_code':code,'output':redact(chunks[:16000].decode(errors='replace')), 'note':reason}

    def inventory(self):
        os_info=Path('/etc/os-release').read_text()[:1500]
        memory=Path('/proc/meminfo').read_text().splitlines()[:3]
        disk=os.statvfs(Path.home())
        return {'os':os_info,'kernel':platform.release(),'architecture':platform.machine(),'cpu_threads':os.cpu_count(),
                'memory':memory,'home_free_gib':round(disk.f_bavail*disk.f_frsize/1024**3,1),
                'desktop':os.environ.get('XDG_CURRENT_DESKTOP','unknown'),
                'scope':list(map(str,self.policy.roots)), 'mode':self.policy.mode}

    def apps(self, query):
        results=[]
        for root in self.read_roots:
            for path in sorted(root.glob('*.desktop')):
                if path.is_symlink(): continue
                try:
                    if path.stat().st_size>65536: continue
                    parser=configparser.ConfigParser(interpolation=None,strict=False); parser.read(path)
                    entry=parser['Desktop Entry']; name=entry.get('Name',path.stem)
                    if query.lower() in (name+' '+path.name).lower():
                        results.append({'name':name,'desktop_file':str(path),'exec':redact(entry.get('Exec',''))})
                except (OSError,KeyError,configparser.Error): continue
                if len(results)>=20: return results
        return results

    def proposal(self, action):
        tool=action['tool']; args=action.get('args',{})
        if self.policy.mode=='inspect': raise Denied('Read-only mode blocks all changes and command execution.')
        if tool=='edit_file':
            path,_,_=self.path(args['path'],True)
            before,info=self.read(str(path),True)
            if info.st_uid != os.getuid(): raise Denied('Only files owned by your user can be edited directly.')
            if digest(before)!=args['sha256']: raise Denied('File changed since inspection. Read it again before proposing an edit.')
            old,new=args['old'],args['new']; text=before.decode()
            if not old or text.count(old)!=1: raise Denied('The exact text to replace must occur once.')
            after=text.replace(old,new,1).encode()
            if len(after)>65536: raise Denied('Edited file exceeds the size limit.')
            difference=''.join(difflib.unified_diff(text.splitlines(True),after.decode().splitlines(True),fromfile=str(path),tofile=str(path)))
            return {'tool':tool,'path':str(path),'sha256':digest(before),'after_sha256':digest(after),'diff':difference,
                    'reason':action.get('reason',''), 'risk':'Changes this file; a rollback copy will be saved.',
                    '_before':before,'_after':after,'_mode':stat.S_IMODE(info.st_mode)}
        if tool=='run_command':
            argv=args.get('argv'); cwd=args.get('cwd')
            if not isinstance(argv,list) or not argv or len(argv)>40 or not all(isinstance(a,str) and '\x00' not in a and len(a)<8000 for a in argv): raise Denied('Provide an argv array with bounded string arguments.')
            if not Path(argv[0]).is_absolute(): raise Denied('Use an absolute executable path.')
            if not cwd: raise Denied('Choose a working directory inside a selected folder.')
            path,_,_=self.path(cwd,True)
            if not path.is_dir(): raise Denied('Working directory must be a selected folder.')
            admin=args.get('admin',False)
            if type(admin) is not bool: raise Denied('admin must be true or false.')
            if admin and not self.policy.allow_admin: raise Denied('Administrator requests are disabled in access settings.')
            return {'tool':tool,'argv':argv,'cwd':str(path),'admin':admin,'reason':action.get('reason',''),
                    'risk':('Runs with administrator access. Stopping an elevated process may require administrator intervention. ' if admin else 'Runs with your user account permissions. ')+'Commands are not sandboxed to selected folders. They may read/change other files, use the network or launch programs. Command side effects have no automatic rollback.'}
        raise Denied('Unknown action.')

    def atomic_replace(self,path,data,mode):
        directory,name,_=self.parent_fd(path,True); temp='.jiezhi-'+uuid.uuid4().hex
        try:
            fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode & 0o777,dir_fd=directory)
            with os.fdopen(fd,'wb') as stream:
                stream.write(data); stream.flush(); os.fchmod(stream.fileno(),mode & 0o777); os.fsync(stream.fileno())
            os.replace(temp,name,src_dir_fd=directory,dst_dir_fd=directory); os.fsync(directory)
        finally:
            try: os.unlink(temp,dir_fd=directory)
            except FileNotFoundError: pass
            os.close(directory)

    def execute(self, action):
        self.check_cancel()
        if not isinstance(action,dict) or not isinstance(action.get('args',{}),dict): raise Denied('Malformed tool proposal.')
        tool=action.get('tool'); args=action.get('args',{})
        self.record('tool',tool=tool,reason=redact(str(action.get('reason','')))[:1000])
        if tool=='inventory': result=self.inventory()
        elif tool=='find_app': result=self.apps(str(args.get('query',''))[:100])
        elif tool=='list_files':
            path,_,_=self.path(args['path']); result=[]
            for child in sorted(path.iterdir()):
                if sensitive(child) or child.is_symlink() or child.name in SKIP_DIRS: continue
                result.append({'name':child.name,'directory':child.is_dir()})
                if len(result)>=100: break
        elif tool=='read_file':
            raw,_=self.read(args['path']); result={'path':args['path'],'sha256':digest(raw),'text':redact(raw.decode())}
        elif tool=='processes':
            result=self.process(['/usr/bin/ps','-eo','pid,comm,%cpu,%mem','--sort=-%cpu'])
            result['output']='\n'.join(result['output'].splitlines()[:21]);result['note']='Top 20 processes by CPU use; arguments are omitted.'
        elif tool=='logs':
            app=str(args.get('app',''))
            if not re.fullmatch(r'[A-Za-z0-9_.@-]{1,100}',app): raise Denied('Use an exact process name or user service unit.')
            argv=['/usr/bin/journalctl','--user','--no-pager','-n','60','--since','-2h','-o','short']
            argv+=['--unit',app] if app.endswith('.service') else ['_COMM='+app]
            result=self.process(argv)
        elif tool=='package_info':
            package=args['name']
            if not re.fullmatch(r'[a-z0-9][a-z0-9+.-]{0,100}',package): raise Denied('Use an exact Debian package name.')
            result=self.process(['/usr/bin/dpkg-query','-W','-f=${Package} ${Version} ${Status}\n',package])
        elif tool in {'edit_file','run_command'}:
            proposal=self.proposal(action); public={k:v for k,v in proposal.items() if not k.startswith('_')}
            self.record('proposed',proposal=redact(json.dumps(public,ensure_ascii=False)))
            auto=tool=='edit_file' and self.policy.mode=='workspace' and not Path(proposal['path']).suffix.lower() in {'.desktop','.service','.timer'} and not Path(proposal['path']).name in {'.bashrc','.profile','.bash_profile','.zshrc'}
            if not auto and not self.approve(public):
                self.record('denied',tool=tool); raise Denied('User denied this action. Do not retry it or use another tool to bypass the decision.')
            self.check_cancel(); self.record('approved',tool=tool,automatic=auto)
            if tool=='edit_file':
                current,_=self.read(proposal['path'],True)
                if digest(current)!=proposal['sha256']: raise Denied('File changed while awaiting approval. Nothing was written.')
                backup_id=uuid.uuid4().hex
                backup={'id':backup_id,'path':proposal['path'],'before':proposal['_before'].decode(),'after_sha256':proposal['after_sha256'],'mode':proposal['_mode']}
                save_json(self.data/'backups'/f'{backup_id}.json',backup)
                self.atomic_replace(proposal['path'],proposal['_after'],proposal['_mode'])
                result={'changed':proposal['path'],'backup_id':backup_id,'sha256':proposal['after_sha256']}
            else:
                result=self.process(proposal['argv'],proposal['cwd'],timeout=90,elevated=proposal['admin'])
        else: raise Denied('Unknown tool. No action was executed.')
        self.record('result',tool=tool,result=redact(json.dumps(result,ensure_ascii=False))[:18000])
        return result

    def undo(self, backup_id):
        if self.policy.mode=='inspect': raise Denied('Read-only mode blocks rollback writes.')
        if not re.fullmatch(r'[a-f0-9]{32}',backup_id): raise Denied('Invalid backup.')
        backup=read_json(self.data/'backups'/f'{backup_id}.json',{})
        current,_=self.read(backup['path'],True)
        if digest(current)!=backup['after_sha256']: raise Denied('File has changed since the assistant edit. Automatic rollback would overwrite newer work.')
        proposal={'tool':'rollback','path':backup['path'],'risk':'Restore the saved contents of this file.',
                  'diff':''.join(difflib.unified_diff(current.decode().splitlines(True),backup['before'].splitlines(True),fromfile='Current',tofile='Restore'))}
        if not self.approve(proposal): raise Denied('Rollback cancelled.')
        self.check_cancel()
        latest,_=self.read(backup['path'],True)
        if latest!=current: raise Denied('File changed during rollback approval.')
        self.atomic_replace(backup['path'],backup['before'].encode(),backup['mode']); self.record('rollback',path=backup['path'],backup_id=backup_id)
        return {'restored':backup['path']}
