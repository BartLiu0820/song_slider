"""Helper preparation boundaries, activation ordering and deployment integration."""
import hashlib
import gzip
import importlib.util
import io
import json
from pathlib import Path
import sys
import ssl
import tarfile
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from test_guards import agent
import helper_client

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'admin'))
import helper_manager as manager
import helper_registry as registry


class ManagerTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root=Path(temp.name);(self.root/'maintenance.lock').touch()
        self.source_hash='a'*64
        for name in manager.FILES:(self.root/name).write_text(name)
        for name,value in [('STATE',self.root),('CONTEXT',self.root),('MAINTENANCE',self.root/'maintenance.lock'),('CURRENT',{'status':'idle'})]:
            p=patch.object(manager,name,value);p.start();self.addCleanup(p.stop)
        self.smoke='\n'.join(hashlib.sha256(name.encode()).hexdigest() for name in manager.FILES[1:])

    def test_requests_cannot_choose_images_commands_or_versions(self):
        for message in [{'action':'run'}, {'action':'ensure','version':'1.0.19'},
                        {'action':'ensure','command':'sh'}, {'action':'ensure','image':'evil'}, []]:
            with self.assertRaises(ValueError):manager.dispatch(message)
        with patch.object(manager.threading,'Thread') as thread:
            manager.dispatch({'action':'ensure'});manager.dispatch({'action':'ensure'})
            self.assertEqual(thread.call_count,1)

    def test_cached_matching_image_avoids_download_and_build(self):
        (self.root/'ready-1.0.18.json').write_text(json.dumps({'source_hash':self.source_hash,'image_id':'id'}))
        with patch.object(manager,'inspect',return_value={'Id':'id'}),patch.object(manager,'run') as run:
            self.assertTrue(manager.prepare('1.0.18',self.source_hash)['cached'])
            run.assert_not_called()

    def test_missing_image_built_and_activated_only_after_smoke(self):
        (self.root/'ready-1.0.18.json').write_text('interrupted receipt')
        with patch.object(manager,'inspect',side_effect=[None,{'Id':'base'},{'Id':'new'}]),\
             patch.object(manager,'fingerprint',return_value=self.source_hash),\
             patch.object(manager,'run',return_value=MagicMock(stdout=self.smoke)) as run:
            self.assertFalse(manager.prepare('1.0.18',self.source_hash)['cached'])
        args=[c.args[0] for c in run.call_args_list]
        self.assertEqual([a[1] for a in args],['build','run','tag'])
        self.assertEqual(args[-1][-1],manager.IMAGE+':1.0.18')
        self.assertEqual(json.loads((self.root/'ready-1.0.18.json').read_text())['image_id'],'new')

    def test_failed_smoke_does_not_replace_existing_image(self):
        with patch.object(manager,'inspect',side_effect=[{'Id':'old'},{'Id':'base'}]),\
             patch.object(manager,'run',return_value=MagicMock(stdout='bad')) as run:
            with self.assertRaisesRegex(ValueError,'checksum'):manager.prepare('1.0.18',self.source_hash)
        self.assertFalse(any(c.args[0][1]=='tag' for c in run.call_args_list))
        self.assertFalse((self.root/'ready-1.0.18.json').exists())

    def test_pull_timeout_uses_verified_fallback_before_build(self):
        def run(args,**kwargs):
            if args[1]=='pull':raise manager.subprocess.TimeoutExpired(args,75)
            return MagicMock(stdout=self.smoke)
        with patch.object(manager,'inspect',side_effect=[None,None,{'RootFS':{'Layers':['verified']}},{'Id':'new'}]),\
             patch.object(manager,'fingerprint',return_value=self.source_hash),\
             patch.object(manager,'run',side_effect=run) as commands,\
             patch.object(manager.platform,'machine',return_value='x86_64'),\
             patch.object(registry,'download',return_value=(self.root/'archive',{'diff_ids':['verified']})) as fallback:
            manager.prepare('1.0.18',self.source_hash)
        fallback.assert_called_once()
        self.assertEqual([c.args[0][1] for c in commands.call_args_list],['pull','load','build','run','tag'])

    def test_imported_filesystem_mismatch_never_activates(self):
        with patch.object(manager,'inspect',side_effect=[None,None,{'RootFS':{'Layers':['wrong']}}]),\
             patch.object(manager,'run',side_effect=[manager.subprocess.TimeoutExpired('pull',75),MagicMock()]) as commands,\
             patch.object(manager.platform,'machine',return_value='x86_64'),\
             patch.object(registry,'download',return_value=(self.root/'archive',{'diff_ids':['verified']})):
            with self.assertRaisesRegex(ValueError,'differs'):manager.prepare('1.0.18',self.source_hash)
        self.assertFalse(any(c.args[0][1] in ['build','tag'] for c in commands.call_args_list))

    def test_version_change_prepares_new_selection_before_ready(self):
        with patch.object(manager,'selected',side_effect=['1.0.18','1.0.19','1.0.19','1.0.19']),\
             patch.object(manager,'fingerprint',return_value=self.source_hash),\
             patch.object(manager,'prepare',return_value={'image_id':'new','cached':False}) as prepare:
            manager.work()
        self.assertEqual([c.args[0] for c in prepare.call_args_list],['1.0.18','1.0.19'])
        self.assertEqual(manager.CURRENT['version'],'1.0.19')
        self.assertEqual(manager.CURRENT['status'],'ready')

    def test_unsafe_source_permissions_rejected(self):
        (self.root/'docker-wrapper').chmod(0o666)
        with self.assertRaises(ValueError):manager.fingerprint()

    def test_failure_details_remain_private(self):
        with patch.object(manager,'selected',side_effect=RuntimeError('private diagnostic')):
            manager.work()
        self.assertEqual(manager.CURRENT['status'],'failed')
        self.assertNotIn('private diagnostic',json.dumps(manager.CURRENT))
        self.assertIn('private diagnostic',(self.root/'last-error.json').read_text())


class ClientTests(unittest.TestCase):
    def test_socket_startup_race_retries_before_giving_up(self):
        error=helper_client.HelperUnavailable('starting');error.__cause__=FileNotFoundError()
        with patch.object(helper_client,'request',side_effect=[error,{'status':'ready'}]) as request,\
             patch.object(helper_client.time,'sleep'):
            self.assertEqual(helper_client.ensure(MagicMock())['status'],'ready')
        self.assertEqual(request.call_count,2)

    def test_ready_waits_for_actual_worker_completion(self):
        statuses=[{'status':'preparing','message':'downloading'},{'status':'ready','version':'1.0.18'}]
        with patch.object(helper_client,'request',side_effect=statuses),patch.object(helper_client.time,'sleep'):
            report=MagicMock();result=helper_client.ensure(report)
        report.assert_called_once_with('downloading');self.assertEqual(result['version'],'1.0.18')

    def test_failure_and_restart_do_not_report_ready(self):
        for status in ['failed','idle']:
            with patch.object(helper_client,'request',return_value={'status':status}):
                with self.assertRaises(helper_client.HelperUnavailable):helper_client.ensure(MagicMock())

    def test_pause_stops_waiting_before_deployment(self):
        with patch.object(helper_client,'request',return_value={'status':'preparing'}):
            self.assertIsNone(helper_client.ensure(MagicMock(),lambda:True))


class AgentHelperTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        for name,value in [('STATE',Path(temp.name))]:
            p=patch.object(agent,name,value);p.start();self.addCleanup(p.stop)
        p=patch.dict(agent.CONFIG,{'helper_preflight_enabled':True});p.start();self.addCleanup(p.stop)
        self.job={'id':'f'*24,'slug':'helper-test','status':'deploying','commit':'b'*40,
                  'application_uuid':'app-id','auto_deploy':True,'plan':{'ready':True,'build_pack':'static',
                  'base_directory':'/','publish_directory':'/','port':80,'generated_files':{}}}
        agent.save(self.job)

    def test_preflight_failure_blocks_submission_without_ai_plan_changes(self):
        original=dict(self.job['plan'])
        with patch.object(agent,'stage_snapshot',return_value=('http://snapshot','c'*40)),\
             patch.object(agent,'local_git'),patch.object(agent,'coolify',return_value={}) as engine,\
             patch.object(helper_client,'ensure',side_effect=helper_client.HelperUnavailable('network failed')),\
             patch.object(agent,'queue_repair') as ai:
            agent.deploy(self.job)
        self.assertFalse(any(c.args[1]=='/deploy' for c in engine.call_args_list))
        ai.assert_not_called()
        job=agent.load(self.job['id'])
        self.assertEqual(job['status'],'failed');self.assertTrue(job['infrastructure_error'])
        self.assertEqual(job['plan'],original)

    def test_ready_preflight_precedes_engine_submission(self):
        order=[]
        def engine(method,path,body=None):
            if path=='/deploy':order.append('submit');return {'deployments':[{'deployment_uuid':'new'}]}
            return {}
        def ready(*args):order.append('helper');return {'status':'ready','version':'1.0.18'}
        with patch.object(agent,'stage_snapshot',return_value=('http://snapshot','c'*40)),\
             patch.object(agent,'local_git'),patch.object(agent,'coolify',side_effect=engine),\
             patch.object(helper_client,'ensure',side_effect=ready):agent.deploy(self.job)
        self.assertEqual(order,['helper','submit'])
        self.assertEqual(agent.load(self.job['id'])['helper_preflight']['version'],'1.0.18')

    def test_engine_version_race_retries_once_without_ai(self):
        self.job['deployment_uuid']='failed-id';agent.save(self.job)
        logs="Preparing container with helper image: song-deploy/coolify-helper:1.0.19\nUnable to find image 'song-deploy/coolify-helper:1.0.19' locally"
        with patch.object(agent,'coolify',return_value={'status':'failed','logs':logs}),\
             patch.object(agent.pool,'submit') as submit,patch.object(agent,'queue_repair') as ai:
            agent.sync_deployment(self.job)
            current=agent.load(self.job['id']);self.assertEqual(current['helper_retries'],1)
            self.assertNotIn('deployment_uuid',current)
            current.update(status='deploying',deployment_uuid='second');agent.save(current)
            agent.sync_deployment(current)
        self.assertEqual(submit.call_count,1);ai.assert_not_called()
        self.assertTrue(agent.load(self.job['id'])['infrastructure_error'])
        self.assertFalse(agent.missing_helper(logs+'\nCloning into repository'))

    def test_restart_in_helper_phase_resumes_but_submit_phase_does_not(self):
        self.job['progress']={'phase':'helper','text':'Preparing helper'};agent.save(self.job)
        with patch.object(agent.pool,'submit') as submit:agent.recover_interrupted();submit.assert_called_once()
        self.job['progress']={'phase':'submit','text':'Submitting deployment'};agent.save(self.job)
        with patch.object(agent.pool,'submit') as submit:agent.recover_interrupted();submit.assert_not_called()

    def test_user_retry_of_infrastructure_error_preserves_plan_and_skips_ai(self):
        self.job.update(status='failed',infrastructure_error=True);agent.save(self.job)
        with agent.app.test_request_context('/',method='POST'),patch.object(agent.pool,'submit') as submit,\
             patch.object(agent,'queue_repair') as ai:
            response,status=agent.retry_repair(self.job['id'])
        self.assertEqual(status,202);ai.assert_not_called()
        self.assertIs(submit.call_args.args[0],agent.deploy)
        self.assertEqual(response.json['plan'],self.job['plan'])


class RegistryTests(unittest.TestCase):
    def test_dns_route_keeps_official_tls_hostname_and_certificate_validation(self):
        connection=registry.routed_connection('pkg-containers.githubusercontent.com','192.0.2.1',timeout=5)
        self.assertEqual(connection.host,'pkg-containers.githubusercontent.com')
        self.assertTrue(connection._context.check_hostname)
        self.assertEqual(connection._context.verify_mode,ssl.CERT_REQUIRED)
        with patch.object(registry.socket,'create_connection') as connect:
            connection._create_connection((connection.host,443),5,None)
        self.assertEqual(connect.call_args.args[0],('192.0.2.1',443))

    def test_registry_cannot_redirect_to_unencrypted_transport(self):
        with self.assertRaisesRegex(ValueError,'non-TLS'):
            registry.Redirect().redirect_request(None,None,302,'',{},'http://example.test')

    def download_fixture(self, root, wrong_range=False, corrupt_layer=False):
        raw=b'filesystem layer for verified archive'
        compressed=gzip.compress(raw)
        digest=lambda data:'sha256:'+hashlib.sha256(data).hexdigest()
        cfg=json.dumps({'architecture':'amd64','os':'linux','rootfs':{'diff_ids':[digest(raw)]}}).encode()
        manifest=json.dumps({'config':{'digest':digest(cfg)},'layers':[{'digest':digest(compressed),
                           'size':len(compressed),'mediaType':'application/vnd.oci.image.layer.v1.tar+gzip'}]}).encode()
        class Response(io.BytesIO):
            def __init__(self,data,headers=None,status=200):
                super().__init__(data);self.headers=headers or {};self.status=status
        def open_request(req,timeout):
            if isinstance(req,str):return Response(b'{"token":"anonymous-test-token"}')
            if '/manifests/' in req.full_url:return Response(manifest,{'Docker-Content-Digest':digest(manifest)})
            if req.full_url.endswith(digest(cfg)):return Response(cfg)
            value=req.get_header('Range')
            start,end=map(int,value.removeprefix('bytes=').split('-'))
            chunk=compressed[start:end+1]
            if corrupt_layer:chunk=b'x'*len(chunk)
            return Response(chunk,{'Content-Range':('bytes 0-0' if wrong_range else f'bytes {start}-{end}')+'/'+str(len(compressed))},206)
        opener=MagicMock();opener.open.side_effect=open_request
        with patch.object(registry.urllib.request,'build_opener',return_value=opener),patch.object(registry,'CHUNK',16),\
             patch.object(registry,'select_route',return_value=None):
            archive,proof=registry.download('1.0.18',root,MagicMock())
        with tarfile.open(archive) as tar:
            files=json.load(tar.extractfile('manifest.json'))[0]
            self.assertEqual(tar.extractfile(files['Layers'][0]).read(),raw)
            self.assertEqual(files['RepoTags'],['ghcr.io/coollabsio/coolify-helper:1.0.18'])
        self.assertEqual(proof['config_digest'],digest(cfg))

    def test_range_download_and_filesystem_archive_verified(self):
        with tempfile.TemporaryDirectory() as root:self.download_fixture(Path(root))

    def test_wrong_range_or_corrupted_layer_never_produces_archive(self):
        for option in ['wrong_range','corrupt_layer']:
            with tempfile.TemporaryDirectory() as root:
                with self.assertRaises(ValueError):self.download_fixture(Path(root),**{option:True})
                self.assertFalse((Path(root)/'helper.tar.gz').exists())

    def test_invalid_version_never_accesses_network(self):
        with patch.object(registry.urllib.request,'build_opener') as opener:
            with self.assertRaises(ValueError):registry.download('1; rm',Path('/tmp'),MagicMock())
            opener.assert_not_called()

    def test_corrupt_content_rejected(self):
        with self.assertRaisesRegex(ValueError,'checksum'):registry.checked(b'corrupt','sha256:'+'a'*64)


if __name__=='__main__':unittest.main()
