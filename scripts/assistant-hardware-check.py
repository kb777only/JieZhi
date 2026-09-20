"""Phone-driven repair test. Approvals are restricted to this disposable fixture."""
import json
import sys
from pathlib import Path
import subprocess
import tempfile
from jiezhi.client import Client
from jiezhi.pc_tools import Tools, Policy, digest
from jiezhi.assistant import Assistant

out=Path('artifacts/v04' if '--9b' in sys.argv else 'artifacts/v03');out.mkdir(exist_ok=True)
root=Path(tempfile.mkdtemp(prefix='jz-v04-')) if '--9b' in sys.argv else Path('.cache/v03-repair-fixture').resolve();root.mkdir(exist_ok=True)
config=root/'settings.json';config.write_text('{"backend":"missing"}\n')
program=root/'demo.py';program.write_text('import json\nfrom pathlib import Path\ns = json.loads(Path("settings.json").read_text())\nif s["backend"] != "safe":\n    raise RuntimeError("Unknown backend; supported backend is safe")\nprint("DEMO STARTED")\n')
program_hash=digest(program.read_bytes())
command=['/usr/bin/python3',str(program)]
baseline=subprocess.run(command,cwd=root,capture_output=True,text=True)
assert baseline.returncode!=0
approvals=[]
def approve(p):
    valid=(p['tool']=='edit_file' and p['path']==str(config)) or (p['tool']=='run_command' and p['argv']==command and p['cwd']==str(root) and not p.get('admin') and digest(program.read_bytes())==program_hash)
    approvals.append({'proposal':p,'accepted':valid});print('APPROVAL',p['tool'],valid,flush=True);return valid
client=Client();status=client.connect('f12b60cc')
if '--9b' in sys.argv:
    selected=next(m for m in status['models'] if '9B' in m['name'])
    status=client.load(selected['id'],'npu',8192)
else:
    assert status.get('loaded_id')
    status=client.load(status['loaded_id'],'npu',8192)
print('TEST MODEL',status['loaded_name'],flush=True)
def event(e):
    if e['kind']=='tool':print('TOOL',e.get('tool'),flush=True)
    if e['kind'] in {'blocked','tool_error','invalid_model_reply'}:print(e,flush=True)
tools=Tools(Policy('confirm',(root,)),approve,event,data=out/'test-audit')
request=f'Fix the startup crash in {program}. Read demo.py and settings.json, repair settings.json only, then verify with exactly /usr/bin/python3 {program} in cwd {root}. Explain the result.'
try:
    answer=Assistant(client,tools,8192).run(request)
    verification=subprocess.run(command,cwd=root,capture_output=True,text=True)
    result={'model':status['loaded_name'],'fixture':str(root),'answer':answer,'approval_count':len(approvals),'accepted_approvals':sum(a['accepted'] for a in approvals),'fixture_starts':verification.returncode==0,'verification_stdout':verification.stdout,'run_id':tools.run_id}
    (out/'assistant-hardware.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
finally:
    # Keep enough context for the new Assistant while leaving the user's model selected.
    client.load(status['loaded_id'],status.get('requested_backend','npu'),4096);client.disconnect()
