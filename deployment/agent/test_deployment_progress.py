"""Static-root correctness and deployment monitoring regressions."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from test_guards import agent


class DeploymentProgressTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        root=Path(tmp.name)
        for obj,key,value in [(agent,'STATE',root),(agent.access,'ROOT',root),(agent.access,'DIRECTORY',root/'security')]:
            p=patch.object(obj,key,value);p.start();self.addCleanup(p.stop)
        self.job={'id':'e'*24,'slug':'progress-test','status':'deploying','deployment_uuid':'current',
                  'repository':'https://github.com/test/example','commit':'b'*40,
                  'plan':{'ready':True,'build_pack':'static','base_directory':'/apps','publish_directory':'/site','port':80}}
        agent.save(self.job)

    def test_static_entry_must_exist_in_combined_directory(self):
        plan=agent.validate_plan(self.job['plan'].copy(),['apps/site/index.html'])
        self.assertEqual(agent.static_directory(plan),'/apps/site')
        with self.assertRaisesRegex(ValueError,'index.html'):
            agent.validate_plan(self.job['plan'].copy(),['index.html'])

    def test_create_and_update_use_static_directory_as_build_context(self):
        for existing in [False,True]:
            job=self.job.copy()
            if existing:job['application_uuid']='app-id'
            calls=[]
            def engine(method,path,body=None):
                calls.append((method,path,body))
                if path=='/applications/public':return {'uuid':'app-id'}
                if path=='/deploy':return {'deployments':[{'deployment_uuid':'new'}]}
                return {}
            with patch.object(agent,'stage_snapshot',return_value=('http://snapshot','c'*40)),patch.object(agent,'local_git'),patch.object(agent,'coolify',side_effect=engine),patch.dict(agent.CONFIG,{'project_uuid':'project','server_uuid':'server'}):
                agent.deploy(job)
            setting=next(body for method,path,body in calls if method in ['POST','PATCH'] and path in ['/applications/public','/applications/app-id'])
            self.assertEqual(setting['base_directory'],'/apps/site');self.assertEqual(setting['publish_directory'],'/')
            self.assertIn('custom_nginx_configuration',setting)
            self.assertTrue(next(body for method,path,body in calls if path=='/deploy')['force'])

    def test_preview_link_changes_with_deployment_to_bypass_old_html_cache(self):
        with agent.app.test_request_context('/',base_url='https://deploy.greatsong.online'):
            first=agent.list_jobs().json[0]['preview_url']
            self.job['deployment_uuid']='next-version';agent.save(self.job)
            second=agent.list_jobs().json[0]['preview_url']
        self.assertTrue(first.endswith('/?deployment=current'))
        self.assertTrue(second.endswith('/?deployment=next-version'))

    def test_existing_custom_nginx_configuration_is_preserved(self):
        job={**self.job,'application_uuid':'app-id'};calls=[]
        def engine(method,path,body=None):
            calls.append((method,path,body))
            if method=='GET':return {'custom_nginx_configuration':'user-managed-config'}
            if path=='/deploy':return {'deployments':[{'deployment_uuid':'new'}]}
            return {}
        with patch.object(agent,'stage_snapshot',return_value=('http://snapshot','c'*40)),patch.object(agent,'local_git'),patch.object(agent,'coolify',side_effect=engine):
            agent.deploy(job)
        self.assertNotIn('custom_nginx_configuration',next(body for method,path,body in calls if method=='PATCH'))

    def test_progress_updates_without_duplicating_phase_events(self):
        agent.progress(self.job,'download','Downloaded 1 MB')
        count=len(agent.read_conversation(self.job['id'])['messages'])
        agent.progress(self.job,'download','Downloaded 2 MB')
        self.assertEqual(len(agent.read_conversation(self.job['id'])['messages']),count)
        self.assertEqual(agent.load(self.job['id'])['progress']['text'],'Downloaded 2 MB')

    def test_logs_sync_automatically_and_redact_secrets(self):
        with patch.object(agent,'coolify',return_value={'status':'in_progress','logs':json.dumps([{'output':'Step 2 token=hidden'}])}):
            agent.sync_deployment(self.job)
        data=agent.read_conversation(self.job['id'])['live_build']
        self.assertEqual(data['logs'],'Step 2 token=[REDACTED]')
        self.assertEqual(agent.load(self.job['id'])['status'],'deploying')

    def test_finished_requires_preview_verification(self):
        with patch.object(agent,'coolify',return_value={'status':'finished','logs':[]}),patch.object(agent,'verify_preview',return_value='首页通过'):
            agent.sync_deployment(self.job)
        self.assertEqual(agent.load(self.job['id'])['status'],'deployed')
        self.assertEqual(agent.load(self.job['id'])['verification'],'首页通过')

    def test_default_page_is_not_success(self):
        self.job['preview_check_started']=0;agent.save(self.job)
        with patch.object(agent,'coolify',return_value={'status':'finished'}),patch.object(agent.urllib.request,'urlopen',return_value=io.BytesIO(b'<h1>Welcome to nginx!</h1>')):
            agent.sync_deployment(self.job)
        self.assertEqual(agent.load(self.job['id'])['status'],'failed')
        self.assertNotIn('deployed_commit',agent.load(self.job['id']))

    def test_old_poll_cannot_overwrite_new_deployment(self):
        newer={**self.job,'deployment_uuid':'newer'};agent.save(newer)
        with patch.object(agent,'coolify',return_value={'status':'finished'}),patch.object(agent,'verify_preview',return_value='ok'):
            agent.sync_deployment(self.job)
        self.assertEqual(agent.load(self.job['id'])['deployment_uuid'],'newer')
        self.assertEqual(agent.load(self.job['id'])['status'],'deploying')
        self.assertNotIn('live_build',agent.read_conversation(self.job['id']))

    def test_engine_error_is_visible_and_next_poll_recovers(self):
        with patch.object(agent,'coolify',side_effect=agent.UpstreamError(503)):
            agent.sync_deployment(self.job)
        self.assertIn('重试',agent.read_conversation(self.job['id'])['live_build']['error'])
        with patch.object(agent,'coolify',return_value={'status':'failed','logs':[{'output':'build failed'}]}):
            agent.sync_deployment(self.job)
        self.assertIsNone(agent.read_conversation(self.job['id'])['live_build']['error'])
        self.assertEqual(agent.load(self.job['id'])['status'],'failed')

    def test_engine_call_does_not_hold_global_state_lock(self):
        def engine(*args):
            self.assertFalse(agent.lock._is_owned())
            return {'status':'in_progress','logs':[]}
        with patch.object(agent,'coolify',side_effect=engine):agent.sync_deployment(self.job)


if __name__=='__main__':unittest.main()
