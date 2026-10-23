"""Deletion boundaries and confirmation regressions; no real Docker mutations."""
import fcntl
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch,MagicMock
from test_guards import agent

spec=importlib.util.spec_from_file_location('cleanup_test',Path(__file__).parents[1]/'admin/cleanup.py')
cleanup=importlib.util.module_from_spec(spec);spec.loader.exec_module(cleanup)
IMAGE='sha256:'+'a'*64

class CleanupTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        for key,value in [('RUNTIME',self.root),('AUDIT',self.root/'audit'),('CURRENT',{'status':'idle'}),('OWNER',None)]:
            p=patch.object(cleanup,key,value);p.start();self.addCleanup(p.stop)
        (self.root/'maintenance.lock').touch()
        self.project={'application_uuid':'app123','slug':'app'}
        self.image={'Id':IMAGE,'RepoTags':['app123:old'],'Size':1000,'SharedSize':400,'Containers':0,'Created':1}
        self.cache={'ID':'cacheabcdefgh','Size':200,'Type':'regular','InUse':False,'Shared':False,'LastUsedAt':'2000-01-01T00:00:00Z'}
        self.owner='b'*64

    def entries(self,**extra):return cleanup.inventory({'Images':[dict(self.image,**extra)],'BuildCache':[self.cache]},[self.project],now=100000)

    def preview(self):
        entries=self.entries();cleanup.CURRENT={'status':'preview','entries':entries,'token':'c'*48,'expires_at':9999999999};cleanup.OWNER=self.owner
        return {'action':'confirm','owner':self.owner,'token':'c'*48,'selected':[entries[0]['key']],'confirm':'清理选中资源'}

    def test_running_and_stopped_container_images_protected(self):
        self.assertFalse(self.entries(Containers=1)[0]['eligible'])
        data={'Images':[self.image],'Containers':[{'ImageID':IMAGE}]}
        self.assertFalse(cleanup.inventory(data,[self.project],100000)[0]['eligible'])

    def test_platform_recent_unknown_size_images_protected(self):
        for change in [{'RepoTags':['nginx:alpine']},{'Created':99999},{'SharedSize':-1},{'Containers':-1}]:
            self.assertFalse(self.entries(**change)[0]['eligible'])
        self.assertEqual(self.entries()[0]['estimated_bytes'],600)

    def test_inuse_shared_recent_cache_protected(self):
        for change in [{'InUse':True},{'Shared':True},{'LastUsedAt':'1970-01-02T03:46:39Z'}]:
            cache={**self.cache,**change}
            self.assertFalse(cleanup.inventory({'BuildCache':[cache]},[],100000)[0]['eligible'])
        self.assertNotIn('Description',self.entries()[1])

    def test_scan_never_mutates_resources(self):
        with patch.object(cleanup,'snapshot',return_value=self.entries()),patch.object(cleanup,'delete_one') as delete:
            cleanup.scan();delete.assert_not_called()
        self.assertEqual(cleanup.CURRENT['status'],'preview')

    def test_confirmation_rejects_wrong_session_token_expiry_or_item(self):
        for change in [{'owner':'d'*64},{'token':'wrong'},{'confirm':True},{'selected':['image:arbitrary']},{'selected':[]},{'selected':['x','x']}]:
            request=self.preview()
            with patch.object(cleanup.threading,'Thread') as thread:
                with self.assertRaises(cleanup.Rejected):cleanup.dispatch({**request,**change})
                thread.assert_not_called()
        request=self.preview();cleanup.CURRENT['expires_at']=1
        with self.assertRaises(cleanup.Rejected):cleanup.dispatch(request)

    def test_confirmation_consumed_once_and_persisted_before_execution(self):
        request=self.preview()
        with patch.object(cleanup.threading,'Thread') as thread:
            cleanup.dispatch(request);cleanup.dispatch(request)
            self.assertEqual(thread.call_count,1)
        state=json.loads((cleanup.AUDIT/'latest.json').read_text())
        self.assertEqual(state['state']['status'],'cleaning')
        self.assertEqual(state['state']['selected'],request['selected'])

    def test_reference_change_aborts_before_any_deletion(self):
        entry=self.entries()[0]
        with patch.object(cleanup,'snapshot',return_value=[{**entry,'eligible':False}]),patch.object(cleanup,'assert_idle'),patch.object(cleanup,'delete_one') as delete:
            cleanup.execute([entry],'test');delete.assert_not_called()
        self.assertEqual(cleanup.CURRENT['status'],'failed')

    def test_active_deployment_aborts_before_deletion(self):
        with patch.object(cleanup,'assert_idle',side_effect=cleanup.Rejected('busy')),patch.object(cleanup,'delete_one') as delete:
            cleanup.execute([self.entries()[0]],'test');delete.assert_not_called()
        self.assertIn('busy',cleanup.CURRENT['message'])

    def test_exact_selection_only_and_no_broad_prune(self):
        image=self.entries()[0]
        with patch.object(cleanup,'docker') as docker:cleanup.delete_one(image)
        self.assertEqual(docker.call_args.args,('DELETE','/images/sha256%3A'+'a'*64+'?force=false&noprune=true'))
        with patch.object(cleanup.subprocess,'run',return_value=MagicMock(returncode=0)) as run:cleanup.delete_one(self.entries()[1])
        args=run.call_args.args[0]
        self.assertIn('id=^cacheabcdefgh$',args);self.assertIn('private=""',args);self.assertNotIn('--all',args)

    def test_execute_only_selected_item_and_reports_verified_removal(self):
        chosen,unselected=self.entries()
        with patch.object(cleanup,'snapshot',side_effect=[[chosen,unselected],[chosen,unselected],[unselected]]),patch.object(cleanup,'assert_idle'),patch.object(cleanup,'delete_one') as delete:
            cleanup.execute([chosen],'successful-test')
        delete.assert_called_once_with(chosen)
        self.assertEqual(cleanup.CURRENT['status'],'complete')
        self.assertEqual(cleanup.CURRENT['report'],[{'key':chosen['key'],'result':'removed'}])

    def test_worker_and_cleanup_lock_exclude_each_other(self):
        with (self.root/'maintenance.lock').open('rb') as handle:
            fcntl.flock(handle,fcntl.LOCK_SH)
            with self.assertRaises(cleanup.Rejected):
                with cleanup.maintenance():pass

    def test_cleanup_api_requires_login_and_csrf(self):
        c=agent.app.test_client()
        self.assertEqual(c.get('/api/cleanup').status_code,401)
        for path in ['/api/cleanup/scan','/api/cleanup/confirm']:self.assertEqual(c.post(path,json={}).status_code,401)
        with c.session_transaction() as session:session['authenticated']=True;session['csrf']='valid'
        self.assertEqual(c.post('/api/cleanup/confirm',json={}).status_code,403)
