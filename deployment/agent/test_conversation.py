"""Conversation, destructive-action and large-source regression checks."""
import hashlib
import io
import json
import os
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch
from test_guards import agent, cfg

class ConversationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name)
        for obj,key,value in [(agent,'STATE',root),(agent.access,'ROOT',root),(agent.access,'DIRECTORY',root/'security')]:
            p=patch.object(obj,key,value);p.start();self.addCleanup(p.stop)
        self.client=agent.app.test_client()
        login=self.client.post('/api/login',json={'email':cfg['email'],'password':'test-password'})
        self.headers={'X-CSRF-Token':login.json['csrf']}
        self.job={'id':'f'*24,'slug':'chat-test','status':'ready','repository':'https://github.com/example/repo',
                  'directory':'/','branch':'main','plan':{'ready':True},'commit':'b'*40}
        agent.save(self.job);self.path='/api/jobs/'+self.job['id']
        agent.chat_pending.clear()

    def post(self,suffix,data):return self.client.post(self.path+suffix,json=data,headers=self.headers)

    def test_conversation_persists_across_worker_save_and_deduplicates_status(self):
        with patch.object(agent.chat_pool,'submit'):
            self.assertEqual(self.post('/chat',{'message':'请帮我看部署方案'}).status_code,202)
            self.assertEqual(self.post('/chat',{'message':'重复请求'}).status_code,409)
        agent.save(self.job)
        response=self.client.get(self.path+'/conversation').json
        self.assertTrue(response['busy']);self.assertEqual(len(response['messages']),2)
        self.assertEqual(response['messages'][-1]['role'],'user')

    def test_ai_only_proposes_allowlisted_action_never_executes(self):
        result={'choices':[{'message':{'content':json.dumps({'reply':'可以删除，请确认','action':'delete'})}}]}
        # Patch only the model-key read; state continues to use real files.
        original=Path.read_text
        def read(path,*a,**kw):return 'test-key' if str(path)=='/etc/song-deploy/deepseek-key' else original(path,*a,**kw)
        for action in ['delete','shell']:
            result['choices'][0]['message']['content']=json.dumps({'reply':'这是建议','action':action})
            with patch.object(agent,'call_json',return_value=result),patch.object(Path,'read_text',read),patch.object(agent,'coolify') as engine:
                agent.answer_chat(self.job['id'],'删除')
                engine.assert_not_called()
            self.assertTrue(agent.job_file(self.job['id']).exists())
            self.assertEqual(agent.read_conversation(self.job['id'])['messages'][-1]['action'],'delete' if action=='delete' else 'none')

    def test_chat_model_failure_is_visible_and_can_retry(self):
        with patch.object(agent,'call_json',side_effect=RuntimeError('AI unavailable')):
            agent.chat_pending.add(self.job['id']);agent.answer_chat(self.job['id'],'帮助')
        self.assertNotIn(self.job['id'],agent.chat_pending)
        self.assertIn('暂时无法完成',agent.read_conversation(self.job['id'])['messages'][-1]['content'])

    def test_auth_and_csrf_protect_new_endpoints(self):
        guest=agent.app.test_client()
        for suffix in ['/chat','/delete']:
            self.assertEqual(guest.post(self.path+suffix,json={}).status_code,401)
            self.assertEqual(self.client.post(self.path+suffix,json={}).status_code,403)
        self.assertEqual(guest.get(self.path+'/conversation').status_code,401)

    def test_delete_requires_exact_confirmation_and_idle_job(self):
        with patch.object(agent,'coolify') as engine:
            self.assertEqual(self.post('/delete',{'confirm':'wrong'}).status_code,400)
            for status in ['queued','analyzing','deploying']:
                agent.save({**self.job,'status':status})
                self.assertEqual(self.post('/delete',{'confirm':self.job['slug']}).status_code,409)
            engine.assert_not_called()

    def test_delete_removes_only_target_and_preserves_volumes(self):
        self.job['application_uuid']='engine-test';agent.save(self.job)
        agent.access.set_policy(self.job['id'],{'mode':'public','accounts':[]})
        repos=agent.STATE/'repos';repos.mkdir();target=repos/(self.job['id']+'-bbbb.git');target.mkdir()
        other=repos/('a'*24+'-bbbb.git');other.mkdir()
        with patch.object(agent,'coolify',return_value={'message':'queued'}) as engine:
            self.assertEqual(self.post('/delete',{'confirm':self.job['slug']}).status_code,200)
        self.assertIn('delete_volumes=false',engine.call_args.args[1])
        self.assertFalse(agent.job_file(self.job['id']).exists());self.assertFalse(target.exists());self.assertTrue(other.exists())
        self.assertFalse(agent.conversation_file(self.job['id']).exists())
        self.assertNotIn(self.job['id'],agent.access.read_security()['policies'])

    def test_delete_upstream_failure_retains_retryable_record(self):
        self.job['application_uuid']='engine-test';agent.save(self.job)
        with patch.object(agent,'coolify',side_effect=agent.UpstreamError(500)):
            self.assertEqual(self.post('/delete',{'confirm':self.job['slug']}).status_code,502)
        self.assertEqual(agent.load(self.job['id'])['status'],'delete_failed')
        self.assertEqual(self.post('/refresh',{}).status_code,409)
        with patch.object(agent,'coolify',side_effect=agent.UpstreamError(404)):
            self.assertEqual(self.post('/delete',{'confirm':self.job['slug']}).status_code,200)

    def test_large_archive_crosses_old_compressed_and_extracted_limits(self):
        # 65 MiB incompressible + 200 MiB zero-filled files exceed both old limits.
        archive=agent.STATE/'fixture.tar.gz'
        class Zeros:
            def read(self,n):return b'\0'*n
        with tarfile.open(archive,'w:gz') as tar:
            blob=os.urandom(65*1024*1024)
            info=tarfile.TarInfo('root/random.bin');info.size=len(blob);tar.addfile(info,io.BytesIO(blob));del blob
            info=tarfile.TarInfo('root/large.bin');info.size=200*1024*1024;tar.addfile(info,Zeros())
        self.assertGreater(archive.stat().st_size,64*1024*1024)
        expected=hashlib.sha256(archive.read_bytes()).hexdigest()
        self.job['tree_sha']='c'*40
        with archive.open('rb') as source,patch.object(agent.urllib.request,'urlopen',return_value=source),patch.object(agent,'local_git',return_value='c'*40):
            result=agent.stage_snapshot(self.job)
        self.assertIn(self.job['id'],result[0]);self.assertEqual(self.job['archive_sha256'],expected)

if __name__=='__main__':unittest.main()
