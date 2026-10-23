"""AI validation feedback, non-index HTML and server deployment regressions."""
import base64
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from test_guards import agent


class PlanRepairTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        root=Path(tmp.name)
        for obj,key,value in [(agent,'STATE',root),(agent.access,'ROOT',root),(agent.access,'DIRECTORY',root/'security')]:
            p=patch.object(obj,key,value);p.start();self.addCleanup(p.stop)
        self.job={'id':'a'*24,'slug':'plan-test','status':'queued','branch':'main',
                  'directory':'/','repository':'https://github.com/test/example'}
        self.entry='04B-prototype-手势小狗探险MVP.html'

    def analyze(self, replies, files):
        calls=[]
        def model(url, body, *args, **kwargs):
            calls.append(copy.deepcopy(body))
            value=replies[min(len(calls)-1,len(replies)-1)]
            return {'choices':[{'message':{'content':value if isinstance(value,str) else json.dumps(value)}}]}
        original=Path.read_text
        def read(path,*args,**kwargs):
            return 'test-key' if str(path)=='/etc/song-deploy/deepseek-key' else original(path,*args,**kwargs)
        with patch.object(agent,'inspect_repository',return_value=('b'*40,files,[])),patch.object(agent,'call_json',side_effect=model),patch.object(Path,'read_text',read):
            agent.analyze(self.job)
        return calls

    def test_bad_static_plan_is_repaired_as_dynamic_without_index(self):
        calls=self.analyze([{'build_pack':'static'},{'build_pack':'nixpacks','port':3000,'start_command':'npm start'}],['package.json','server.js'])
        self.assertEqual(self.job['status'],'ready')
        self.assertEqual(self.job['plan']['build_pack'],'nixpacks')
        self.assertIn('validation_error',calls[1]['messages'][-1]['content'])
        self.assertEqual(len(self.job['analysis_attempts']),2)

    def test_readme_entry_can_replace_missing_index(self):
        self.analyze([{'build_pack':'static'},{'build_pack':'static','static_entry':self.entry}],[self.entry])
        self.assertEqual(self.job['status'],'ready')
        self.assertEqual(self.job['plan']['static_entry'],self.entry)
        self.assertIn(self.entry,agent.static_nginx(self.job['plan']))

    def test_invalid_json_is_repairable(self):
        self.analyze(['invalid JSON',{'build_pack':'nixpacks','port':8000}],['app.py'])
        self.assertEqual(self.job['status'],'ready')

    def test_repeated_bad_plan_is_bounded_and_not_deployable(self):
        calls=self.analyze([{'build_pack':'static'}],['server.js'])
        self.assertEqual(len(calls),3)
        self.assertEqual(self.job['status'],'failed')
        self.assertNotIn('plan',self.job)
        self.assertIn('2 次',self.job['error'])

    def test_repair_keeps_real_configuration_requirements(self):
        self.analyze([{'build_pack':'static'},{'build_pack':'nixpacks','missing_env':['API_KEY']}],['app.py'])
        self.assertEqual(self.job['status'],'needs_configuration')
        self.assertFalse(self.job['plan']['ready'])

    def test_entry_path_and_nginx_injection_are_rejected(self):
        for entry in ['../index.html','/index.html','a/entry.html','a";return 200;.html','$uri.html','x\n.html','x\\.html']:
            with self.subTest(entry=entry),self.assertRaises(ValueError):
                agent.validate_plan({'build_pack':'static','static_entry':entry},[entry])

    def test_static_build_commands_are_not_silently_ignored(self):
        with self.assertRaisesRegex(ValueError,'nixpacks'):
            agent.validate_plan({'build_pack':'static','build_command':'npm run build'},['index.html'])

    def test_browser_dependencies_require_install_before_publish(self):
        context=[{'path':'gesture.mjs','content':'import {Vision} from "./node_modules/vision/bundle.mjs";'}]
        files=['index.html','gesture.mjs','package.json']
        with self.assertRaisesRegex(ValueError,'尚未安装'):
            agent.validate_plan({'build_pack':'static'},files,context)
        agent.validate_plan({'build_pack':'static'},files+['node_modules/vision/bundle.mjs'],context)
        plan=agent.validate_plan({'build_pack':'nixpacks','is_static':True,'install_command':'npm ci --omit=dev'},files,context)
        body,git=self.deploy(plan)
        self.assertTrue(body['is_static'])
        self.assertEqual(body['install_command'],'npm ci --omit=dev')
        self.assertIn('custom_nginx_configuration',body)
        git.assert_not_called()

    def test_frontend_build_output_need_not_exist_in_source(self):
        plan=agent.validate_plan({'build_pack':'nixpacks','is_static':True,'publish_directory':'/dist',
                                  'build_command':'npm run build'},['package.json','src/main.js'])
        body,_=self.deploy(plan)
        self.assertEqual(body['base_directory'],'/')
        self.assertEqual(body['publish_directory'],'/dist')
        self.assertTrue(body['is_static'])

    def test_named_entry_must_exist_in_published_directory(self):
        p={'build_pack':'static','base_directory':'/apps','publish_directory':'/game','static_entry':self.entry}
        agent.validate_plan(p.copy(),['apps/game/'+self.entry])
        with self.assertRaises(ValueError):agent.validate_plan(p.copy(),[self.entry])

    def deploy(self, plan, existing=None):
        job={**self.job,'commit':'b'*40,'status':'deploying','plan':plan}
        if existing is not None:job.update(application_uuid='app-id',managed_static_nginx=existing)
        calls=[]
        def engine(method,path,body=None):
            calls.append((method,path,body))
            if method=='GET':return {'custom_nginx_configuration':existing}
            if path=='/applications/public':return {'uuid':'app-id'}
            if path=='/deploy':return {'deployments':[{'deployment_uuid':'new'}]}
            return {}
        with patch.object(agent,'stage_snapshot',return_value=('http://snapshot','c'*40)),patch.object(agent,'local_git') as git,patch.object(agent,'coolify',side_effect=engine),patch.dict(agent.CONFIG,{'project_uuid':'project','server_uuid':'server'}):
            agent.deploy(job)
        self.assertEqual(job['status'],'deploying',job.get('error'))
        body=next(body for method,path,body in calls if method in ['POST','PATCH'] and path in ['/applications/public','/applications/app-id'])
        return body,git

    def test_dynamic_create_and_switch_do_not_check_static_entry(self):
        for pack in ['nixpacks','dockerfile']:
            for existing in [None,'old-static-config']:
                plan={'ready':True,'build_pack':pack,'base_directory':'/api','publish_directory':'/', 'port':8000,'start_command':'python main.py'}
                body,git=self.deploy(plan,existing)
                git.assert_not_called()
                self.assertFalse(body['is_static'])
                self.assertEqual(body['base_directory'],'/api')
                self.assertEqual(body['start_command'],'python main.py')

    def test_managed_entry_changes_on_redeploy(self):
        plan={'ready':True,'build_pack':'static','base_directory':'/','publish_directory':'/','port':80,'static_entry':self.entry}
        previous=agent.static_nginx({})
        body,git=self.deploy(plan,previous)
        self.assertIn(self.entry,base64.b64decode(body['custom_nginx_configuration']).decode())
        self.assertTrue(git.call_args.args[0][-1].endswith(self.entry))


if __name__=='__main__':unittest.main()
