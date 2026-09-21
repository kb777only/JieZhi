import hashlib
import json
from pathlib import Path
import threading
import pytest
from jiezhi.pc_tools import Tools, Policy, Denied, Cancelled
from jiezhi.assistant import Assistant, parse_reply


def toolset(tmp_path, mode='confirm', approve=lambda p:False):
    root=tmp_path/'workspace';root.mkdir(exist_ok=True)
    return Tools(Policy(mode,(root,)),approve,data=tmp_path/'private'),root


def edit(tool,path,old,new):
    read=tool.execute({'tool':'read_file','args':{'path':str(path)}})
    return {'tool':'edit_file','args':{'path':str(path),'sha256':read['sha256'],'old':old,'new':new},'reason':'Repair config'}


def test_modes_approval_and_undo(tmp_path):
    proposals=[]; t,root=toolset(tmp_path,approve=lambda p:proposals.append(p) or True)
    path=root/'config.ini';path.write_text('backend=broken\n')
    action=edit(t,path,'broken','safe');result=t.execute(action)
    assert path.read_text()=='backend=safe\n' and proposals[0]['diff']
    t.undo(result['backup_id']);assert path.read_text()=='backend=broken\n'
    t,root=toolset(tmp_path,'inspect',lambda p:pytest.fail('Read-only must not request approval'))
    with pytest.raises(Denied,match='Read-only'):t.execute(action)
    t,root=toolset(tmp_path,approve=lambda p:False)
    with pytest.raises(Denied,match='denied'):t.execute(action)
    assert path.read_text()=='backend=broken\n'


def test_auto_edits_only_selected_roots_and_commands_always_ask(tmp_path):
    t,root=toolset(tmp_path,'workspace',lambda p:False)
    path=root/'config.ini';path.write_text('bad=true')
    assert t.execute(edit(t,path,'true','false'))['backup_id']
    with pytest.raises(Denied,match='denied'):
        t.execute({'tool':'run_command','args':{'argv':['/usr/bin/touch',str(root/'should-not-exist')],'cwd':str(root)}})
    assert not (root/'should-not-exist').exists()
    outside=tmp_path/'outside.txt';outside.write_text('private')
    with pytest.raises(Denied,match='outside'):t.execute({'tool':'read_file','args':{'path':str(outside)}})


def test_symlinks_hardlinks_credentials_and_traversal_blocked(tmp_path):
    t,root=toolset(tmp_path)
    outside=tmp_path/'outside';outside.write_text('secret')
    (root/'link').symlink_to(outside)
    import os
    os.link(outside,root/'hardlink')
    (root/'.env').write_text('TOKEN=secret')
    for path in [root/'link',root/'hardlink',root/'.env',root/'..'/'outside']:
        with pytest.raises(Denied):t.execute({'tool':'read_file','args':{'path':str(path)}})
    assert outside.read_text()=='secret'


def test_edit_revalidates_after_approval_and_undo_preserves_new_work(tmp_path):
    t,root=toolset(tmp_path);path=root/'config';path.write_text('original')
    action=edit(t,path,'original','fixed')
    def concurrent_change(p):path.write_text('user edit');return True
    t.approve=concurrent_change
    with pytest.raises(Denied,match='changed'):t.execute(action)
    assert path.read_text()=='user edit'
    t.approve=lambda p:True;result=t.execute(edit(t,path,'user edit','fixed'))
    path.write_text('newer work')
    with pytest.raises(Denied,match='newer work'):t.undo(result['backup_id'])
    assert path.read_text()=='newer work'


def test_stop_and_admin_guard(tmp_path):
    t,root=toolset(tmp_path,approve=lambda p:True)
    action={'tool':'run_command','args':{'argv':['/usr/bin/true'],'cwd':str(root),'admin':True}}
    with pytest.raises(Denied,match='Administrator'):t.execute(action)
    t.cancel.set()
    with pytest.raises(Cancelled):t.execute({'tool':'inventory'})


def test_command_timeout_and_output_bounds(tmp_path):
    t,root=toolset(tmp_path)
    result=t.process(['/bin/sh','-c','sleep 4'],cwd=root,timeout=.1)
    assert 'timed out' in result['note'] and result['exit_code']!=0
    result=t.process(['/usr/bin/printf','hello'])
    assert result['output']=='hello' and result['exit_code']==0


def test_model_cannot_bypass_permission_with_unrecognized_tools(tmp_path):
    assert parse_reply('```json\n{"answer":"done"}\n```')=={'answer':'done'}
    assert parse_reply('Reasoning already opened by the template.\n</think>\n{"tool":"read_file","args":{"path":"/tmp/demo.py"}}')['tool']=='read_file'
    assert parse_reply('<think>{"tool":"run_command","args":{}}</think>{"answer":"done"}')=={'answer':'done'}
    with pytest.raises(ValueError):parse_reply('<think>{"tool":"run_command","args":{}}')
    with pytest.raises(ValueError):parse_reply('Prose {"tool":"run_command","args":{}}')
    with pytest.raises(ValueError):parse_reply('{"tool":"read_file","args":{},"approved":true}')
    t,_=toolset(tmp_path)
    with pytest.raises(Denied,match='Unknown'):t.execute({'tool':'grant_access','args':{'path':'/'}})


def test_agent_repairs_fixture_and_verifies_with_approved_command(tmp_path):
    approvals=[];t,root=toolset(tmp_path,approve=lambda p:approvals.append(p) or True)
    path=root/'config.json';path.write_text('{"backend":"broken"}')
    code='import json; from pathlib import Path; assert json.loads(Path("config.json").read_text())["backend"] == "safe"; print("STARTED")'
    actions=[{'tool':'read_file','args':{'path':str(path)}},edit(t,path,'broken','safe'),
             {'tool':'run_command','args':{'argv':['/usr/bin/python3','-c',code],'cwd':str(root)}},
             {'answer':'Updated the backend and verified STARTED with exit code 0.'}]
    class FakePhone:
        def cancel(self):pass
        def chat(self,messages,emit,max_tokens):emit({'type':'token','text':json.dumps(actions.pop(0))})
    answer=Assistant(FakePhone(),t,8192).run('Repair the startup failure and verify.')
    assert 'verified' in answer and len(approvals)==2
    assert json.loads(path.read_text())['backend']=='safe'
    records=json.loads(next((tmp_path/'private/runs').glob('*.json')).read_text())
    assert any(e['kind']=='result' and 'STARTED' in e['result'] for e in records['events'])


def test_invalid_model_and_denial_stop_without_retry(tmp_path):
    t,root=toolset(tmp_path)
    class BadPhone:
        def chat(self,messages,emit,max_tokens):emit({'type':'token','text':'run rm -rf /'})
    assert 'valid tool instructions' in Assistant(BadPhone(),t,8192).run('Inspect PC')
    class DeniedPhone:
        calls=0
        def cancel(self):pass
        def chat(self,messages,emit,max_tokens):
            self.calls+=1;emit({'type':'token','text':json.dumps({'tool':'run_command','args':{'argv':['/usr/bin/true'],'cwd':str(root)}})})
    phone=DeniedPhone();assert 'User denied' in Assistant(phone,t,8192).run('Test')
    assert phone.calls==1


def test_agent_stops_at_first_complete_final_action(tmp_path):
    t,root=toolset(tmp_path)
    class ReasoningPhone:
        cancelled=False
        def cancel(self):self.cancelled=True
        def chat(self,messages,emit,max_tokens):
            for chunk in ['<think>{"tool":"run_command","args":{}}', '</think>', '{"answer":', '"No changes needed."}']:
                assert not self.cancelled
                emit({'type':'token','text':chunk})
            assert self.cancelled
            emit({'type':'token','text':'extra unwanted repetition'})
            emit({'type':'done','cancelled':True})
    answer=Assistant(ReasoningPhone(),t,8192).run('Inspect only')
    assert 'No changes needed.' in answer and '0 command(s)' in answer


def test_create_files_and_folders_review_undo_and_scope(tmp_path):
    approvals=[]
    t,root=toolset(tmp_path,approve=lambda p:approvals.append(p) or True)
    folder=root/'src';path=folder/'main.py'
    t.execute({'tool':'create_directory','args':{'path':str(folder)}})
    result=t.execute({'tool':'create_file','args':{'path':str(path),'content':'print("hello")\n'}})
    assert path.read_text()=='print("hello")\n' and len(approvals)==2
    assert '+print("hello")' in approvals[-1]['diff']
    with pytest.raises(Denied,match='already exists'):
        t.execute({'tool':'create_file','args':{'path':str(path),'content':'overwrite'}})
    t.undo(result['backup_id']);assert not path.exists()
    for destination in [tmp_path/'escape.py',root/'..'/'escape.py',root/'.env',root/'.git'/'config']:
        with pytest.raises(Denied):t.execute({'tool':'create_file','args':{'path':str(destination),'content':'x'}})
    (root/'link').symlink_to(tmp_path,target_is_directory=True)
    with pytest.raises(Denied):t.execute({'tool':'create_file','args':{'path':str(root/'link'/'escape.py'),'content':'x'}})
    assert not (tmp_path/'escape.py').exists()


def test_create_modes_and_approval_race_preserve_existing_work(tmp_path):
    t,root=toolset(tmp_path)
    path=root/'new.txt';action={'tool':'create_file','args':{'path':str(path),'content':'model work'}}
    with pytest.raises(Denied,match='denied'):t.execute(action)
    assert not path.exists()
    t,_=toolset(tmp_path,'inspect')
    with pytest.raises(Denied,match='Read-only'):t.execute(action)
    t,_=toolset(tmp_path,'workspace',lambda p:pytest.fail('Safe creation should follow scoped autonomy'))
    assert t.execute(action)['changed']==str(path)
    path.unlink()
    def concurrent_create(proposal):path.write_text('user work');return True
    t,_=toolset(tmp_path,approve=concurrent_create)
    with pytest.raises(FileExistsError):t.execute(action)
    assert path.read_text()=='user work'


def test_project_agent_creates_edits_and_verifies_real_file(tmp_path):
    approvals=[];t,root=toolset(tmp_path,approve=lambda p:approvals.append(p) or True)
    path=root/'hello.py'
    actions=[{'tool':'create_file','args':{'path':str(path),'content':'print("hello")\n'}},
             {'tool':'read_file','args':{'path':str(path)}},
             {'tool':'edit_file','args':{'path':str(path),'old':'hello','new':'world'}},
             {'tool':'run_command','args':{'argv':['/usr/bin/python3',str(path)],'cwd':str(root)}},
             {'answer':'Saved hello.py and verified it prints world.'}]
    class Phone:
        def cancel(self):pass
        def chat(self,messages,emit,max_tokens):
            assert 'create_file' in messages[0]['content'] and 'manual file creation instructions' in messages[0]['content']
            emit({'type':'token','text':json.dumps(actions.pop(0))})
    answer=Assistant(Phone(),t,8192).run('Make a hello world program.',project=True)
    assert '2 file change(s), 1 command(s)' in answer
    assert path.read_text()=='print("world")\n' and len(approvals)==3


def test_edit_empty_file_requires_inspection_and_approval(tmp_path):
    t,root=toolset(tmp_path,approve=lambda p:True)
    path=root/'empty.txt';path.touch()
    t.execute(edit(t,path,'','New contents'))
    assert path.read_text()=='New contents'
