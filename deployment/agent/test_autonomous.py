"""Autonomous lifecycle, real derived Git snapshots, and repair isolation."""
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from test_guards import agent, cfg


class AutonomousTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        root=Path(tmp.name)
        for obj,key,value in [(agent,'STATE',root),(agent.access,'ROOT',root),(agent.access,'DIRECTORY',root/'security')]:
            p=patch.object(obj,key,value);p.start();self.addCleanup(p.stop)
        self.files=['package.json','server.js','src/server.js']
        self.plan=agent.validate_plan({'build_pack':'nixpacks','port':3000,'start_command':'node wrong.js'},self.files)
        self.job={'id':'1'*24,'slug':'auto-test','repository':'https://github.com/test/example',
                  'directory':'/','branch':'main','commit':'b'*40,'status':'failed','plan':self.plan,
                  'auto_deploy':True,'repair_attempts':[],'deployment_uuid':'broken',
                  'error':'Cannot find module wrong.js'}
        agent.save(self.job);agent.save_source_context(self.job,self.files,[{'path':'package.json','content':'{"scripts":{"start":"node server.js"}}'}])
        original=Path.read_text
        def read(path,*a,**kw):return 'test-key' if str(path)=='/etc/song-deploy/deepseek-key' else original(path,*a,**kw)
        p=patch.object(Path,'read_text',read);p.start();self.addCleanup(p.stop)

    def run_repair(self,replies):
        self.job['status']='repairing';agent.save(self.job)
        calls=[]
        def model(url,body,*a,**kw):
            calls.append(copy.deepcopy(body))
            value=replies[min(len(calls)-1,len(replies)-1)]
            return {'choices':[{'message':{'content':json.dumps(value)}}]}
        with patch.object(agent,'call_json',side_effect=model),patch.object(agent,'deploy') as deploy:
            agent.repair_deployment(self.job['id'])
        return agent.load(self.job['id']),calls,deploy

    def test_build_failure_queues_once_and_stale_poll_cannot_enqueue_twice(self):
        self.job['status']='deploying';agent.save(self.job)
        with patch.object(agent,'coolify',return_value={'status':'failed','logs':'Cannot find module wrong.js'}),patch.object(agent.pool,'submit') as submit:
            agent.sync_deployment(self.job);agent.sync_deployment(self.job)
        self.assertEqual(submit.call_count,1)
        self.assertEqual(agent.load(self.job['id'])['status'],'repairing')

    def test_failed_command_is_revised_and_redeployed_automatically(self):
        updated={**self.plan,'start_command':'node server.js'}
        job,calls,deploy=self.run_repair([{'action':'revise','reason':'package.json 的入口为 server.js，日志的 wrong.js 不存在','plan':updated}])
        deploy.assert_called_once();self.assertEqual(job['status'],'deploying')
        self.assertNotIn('deployment_uuid',job)
        self.assertEqual(job['plan']['start_command'],'node server.js')
        self.assertEqual(job['commit'],'b'*40)
        self.assertTrue(job['repair_attempts'][0]['submitted'])
        self.assertIn('wrong.js',calls[0]['messages'][1]['content'])

    def test_repeated_plan_gets_validation_feedback_without_redeploy(self):
        job,calls,deploy=self.run_repair([{'action':'revise','reason':'重复旧方案','plan':self.plan}])
        self.assertEqual(len(calls),4);deploy.assert_not_called()
        self.assertIn('已经失败',calls[1]['messages'][-1]['content'])
        self.assertEqual(job['status'],'needs_attention')

    def test_transient_retry_allowed_only_once_per_run(self):
        self.job['repair_attempts']=[{'number':1,'action':'retry','submitted':True}]
        job,_,deploy=self.run_repair([{'action':'retry','reason':'网络连接超时'}])
        deploy.assert_not_called();self.assertEqual(job['status'],'needs_attention')

    def test_missing_key_is_concrete_question_not_fake_success(self):
        job,_,deploy=self.run_repair([{'action':'needs_input','reason':'支付接口缺少凭据','question':'请在环境变量中配置 PAYMENT_KEY 后继续。'}])
        deploy.assert_not_called();self.assertEqual(job['status'],'needs_attention')
        self.assertIn('PAYMENT_KEY',job['error'])
        self.assertNotIn('deployed_commit',job)

    def test_four_attempt_budget_stops_without_requeue(self):
        self.job['repair_attempts']=[{'number':i} for i in range(1,5)];agent.save(self.job)
        with patch.object(agent.pool,'submit') as submit:agent.queue_repair(self.job)
        submit.assert_not_called();self.assertEqual(agent.load(self.job['id'])['status'],'needs_attention')

    def test_autonomous_analysis_continues_to_deploy(self):
        model={'choices':[{'message':{'content':json.dumps(self.plan)}}]}
        with patch.object(agent,'inspect_repository',return_value=('b'*40,self.files,[])),patch.object(agent,'call_json',return_value=model),patch.object(agent,'deploy') as deploy:
            agent.analyze(self.job)
        deploy.assert_called_once();self.assertEqual(self.job['status'],'deploying')

    def test_initial_missing_config_does_not_submit_build(self):
        model={'choices':[{'message':{'content':json.dumps({**self.plan,'missing_env':['PAYMENT_KEY']})}}]}
        with patch.object(agent,'inspect_repository',return_value=('b'*40,self.files,[])),patch.object(agent,'call_json',return_value=model),patch.object(agent,'deploy') as deploy:
            agent.analyze(self.job)
        deploy.assert_not_called();self.assertEqual(self.job['status'],'needs_configuration')

    def test_generated_dockerfile_valid_but_escape_and_source_edits_rejected(self):
        plan={'build_pack':'dockerfile','port':8000,'dockerfile_location':'/.song-deploy/Dockerfile',
              'generated_files':{'.song-deploy/Dockerfile':'FROM python:3.12-slim\nCOPY . /app\n'}}
        agent.validate_plan(plan,[])
        for name in ['../Dockerfile','Dockerfile','server.js','.song-deploy/../../etc/file','.song-deploy/secret.env']:
            with self.subTest(name=name),self.assertRaises(ValueError):
                agent.validate_plan({**plan,'generated_files':{name:'content'}},[])

    def test_dockerfile_cannot_be_wrapped_again_as_static_build(self):
        with self.assertRaisesRegex(ValueError,'is_static=false'):
            agent.validate_plan({'build_pack':'dockerfile','is_static':True},['Dockerfile'])

    def test_derived_snapshot_preserves_upstream_and_is_reproducible(self):
        repos=agent.STATE/'repos';repos.mkdir();work=agent.STATE/'fixture';work.mkdir()
        (work/'server.js').write_text('original source')
        agent.local_git(['init','-b','main'],work);agent.local_git(['add','.'],work)
        agent.local_git(['-c','user.name=test','-c','user.email=test@example.com','commit','-m','fixture'],work)
        original=repos/(self.job['id']+'-'+self.job['commit'][:12]+'.git')
        agent.local_git(['clone','--bare',str(work),str(original)])
        before=agent.local_git(['--git-dir',str(original),'rev-parse','HEAD^{tree}'])
        self.job['plan']=agent.validate_plan({'build_pack':'dockerfile','port':3000,
            'dockerfile_location':'/.song-deploy/Dockerfile','generated_files':{'.song-deploy/Dockerfile':'FROM node:22-alpine\nCOPY . /app\n'}},self.files)
        commit=agent.local_git(['--git-dir',str(original),'rev-parse','HEAD'])
        one=agent.stage_generated_snapshot(self.job,'http://original',commit)
        two=agent.stage_generated_snapshot(self.job,'http://original',commit)
        self.assertEqual(one,two);self.assertNotEqual(one[1],commit)
        self.assertEqual(before,agent.local_git(['--git-dir',str(original),'rev-parse','HEAD^{tree}']))
        derived=original
        self.assertEqual(agent.local_git(['--git-dir',str(derived),'show','HEAD:server.js']),'original source')
        self.assertIn('FROM node',agent.local_git(['--git-dir',str(derived),'show',one[1]+':.song-deploy/Dockerfile']))

    def test_read_files_only_pinned_source_no_secret_or_arbitrary_url(self):
        with patch.object(agent,'call_json') as fetch:
            for name in ['../../etc/passwd','https://evil.test/file','.env','.env.production']:
                with self.assertRaises(ValueError):agent.read_repair_files(self.job,[name],self.files+['.env','.env.production'])
        fetch.assert_not_called()
        import base64
        with patch.object(agent,'call_json',return_value={'type':'file','size':10,'content':base64.b64encode(b'code').decode()}) as fetch:
            agent.read_repair_files(self.job,['server.js'],self.files)
        self.assertIn('?ref='+'b'*40,fetch.call_args.args[0])

    def test_diagnostics_redact_app_values_and_separate_runtime_scope(self):
        self.job['application_uuid']='app'
        data=agent.read_conversation(self.job['id']);data['live_build']={'logs':'connecting supersecret-value to https://user:pass@db.test'};agent.write_conversation(self.job['id'],data)
        with patch.object(agent,'coolify',side_effect=[[{'key':'DB_PASSWORD','value':'supersecret-value'}],{'logs':'DB supersecret-value'}]):
            result=agent.repair_diagnostics(self.job)
        self.assertNotIn('supersecret-value',json.dumps(result));self.assertNotIn('user:pass',json.dumps(result))
        self.assertIn('上次成功',result['runtime_log_scope'])

    def test_no_runtime_container_does_not_hide_available_build_diagnostics(self):
        self.job['application_uuid']='app'
        data=agent.read_conversation(self.job['id']);data['live_build']={'logs':'build failed at COPY h5'};agent.write_conversation(self.job['id'],data)
        with patch.object(agent,'coolify',side_effect=[[],agent.UpstreamError(404)]):
            result=agent.repair_diagnostics(self.job)
        self.assertIn('COPY h5',result['build_logs'])
        self.assertIn('尚无',result['runtime_logs'])

    def test_unknown_env_values_withhold_logs_from_model(self):
        self.job['application_uuid']='app'
        data=agent.read_conversation(self.job['id']);data['live_build']={'logs':'private-value'};agent.write_conversation(self.job['id'],data)
        with patch.object(agent,'coolify',side_effect=agent.UpstreamError(500)):
            result=agent.repair_diagnostics(self.job)
        self.assertNotIn('private-value',json.dumps(result))

    def test_health_endpoint_and_memory_validation(self):
        for value in ['//evil.test','/../secret','/health?token=x','/health\n']:
            with self.subTest(value=value),self.assertRaises(ValueError):agent.validate_plan({**self.plan,'health_check_path':value},self.files)
        for value in [True,10,100000]:
            with self.assertRaises(ValueError):agent.validate_plan({**self.plan,'memory_mb':value},self.files)
        self.job['plan']['health_check_path']='/health'
        with patch.object(agent.urllib.request,'urlopen',return_value=io.BytesIO(b'ok')) as fetch:
            agent.verify_preview(self.job)
        self.assertEqual(fetch.call_args.args[0].full_url,'http://127.0.0.1/health')

    def test_restart_resumes_repair_but_not_uncertain_submission(self):
        self.job['status']='repairing';agent.save(self.job)
        with patch.object(agent.pool,'submit') as submit:agent.recover_interrupted()
        submit.assert_called_once_with(agent.repair_deployment,self.job['id'])
        self.job['status']='deploying';self.job.pop('deployment_uuid');agent.save(self.job)
        with patch.object(agent.pool,'submit') as submit:agent.recover_interrupted()
        submit.assert_not_called();self.assertEqual(agent.load(self.job['id'])['status'],'needs_attention')

    def test_chat_execution_requires_explicit_model_execute_and_preserves_busy_guard(self):
        self.job['status']='ready';agent.save(self.job)
        result={'choices':[{'message':{'content':json.dumps({'reply':'准备部署','action':'deploy','execute':True})}}]}
        with patch.object(agent,'call_json',return_value=result),patch.object(agent.pool,'submit') as submit:
            agent.answer_chat(self.job['id'],'请部署')
        submit.assert_called_once();self.assertEqual(agent.load(self.job['id'])['status'],'deploying')
        with patch.object(agent,'call_json',return_value=result),patch.object(agent.pool,'submit') as submit:
            agent.answer_chat(self.job['id'],'再部署')
        submit.assert_not_called()

    def test_pause_marker_survives_stale_worker_and_prevents_new_build(self):
        agent.automation_marker(self.job['id']).touch()
        agent.save(self.job)  # A worker snapshot cannot erase the separate control.
        with patch.object(agent.pool,'submit') as submit:agent.queue_repair(self.job)
        submit.assert_not_called()
        with patch.object(agent,'coolify') as engine:agent.deploy(self.job)
        engine.assert_not_called();self.assertEqual(self.job['status'],'cancelled')

    def test_new_project_enables_automatic_deployment(self):
        client=agent.app.test_client()
        logged=client.post('/api/login',json={'email':cfg['email'],'password':'test-password'})
        with patch.object(agent.pool,'submit'):
            response=client.post('/api/analyze',json={'repository':'https://github.com/test/new','slug':'new-project'},headers={'X-CSRF-Token':logged.json['csrf']})
        self.assertEqual(response.status_code,202);self.assertTrue(response.json['auto_deploy'])

    def test_repair_endpoint_enforces_auth_csrf_and_busy_state(self):
        client=agent.app.test_client();url='/api/jobs/'+self.job['id']+'/repair'
        self.assertEqual(client.post(url,json={}).status_code,401)
        logged=client.post('/api/login',json={'email':cfg['email'],'password':'test-password'})
        self.assertEqual(client.post(url,json={}).status_code,403)
        self.job['status']='repairing';agent.save(self.job)
        self.assertEqual(client.post(url,json={},headers={'X-CSRF-Token':logged.json['csrf']}).status_code,409)


if __name__=='__main__':unittest.main()
