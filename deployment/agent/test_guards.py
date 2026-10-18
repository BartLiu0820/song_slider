"""Security boundaries for AI proposals and deployment requests (no real API)."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
import io
import tarfile
from unittest.mock import patch

tmp=tempfile.TemporaryDirectory()
root=Path(tmp.name);salt='11'*16
cfg={'session_secret':'isolated-test-secret','email':'test@example.com','password_salt':salt,
     'password_hash':hashlib.pbkdf2_hmac('sha256',b'test-password',bytes.fromhex(salt),600000).hex()}
(root/'config.json').write_text(json.dumps(cfg))
os.environ['SONG_CONFIG']=str(root/'config.json');os.environ['SONG_STATE']=str(root/'state')
spec=importlib.util.spec_from_file_location('agent_under_test',Path(__file__).with_name('app.py'))
agent=importlib.util.module_from_spec(spec);spec.loader.exec_module(agent)


class GuardTests(unittest.TestCase):
    def test_repository_boundaries(self):
        for url in ['http://127.0.0.1/x','https://github.com@evil.test/a/b',
                    'file:///etc/passwd','https://github.com/a/b?token=x','https://github.com/../b']:
            with self.assertRaises(ValueError):agent.repository_url(url)
        self.assertEqual(agent.repository_url('https://github.com/pallets/flask.git'),'https://github.com/pallets/flask')

    def test_paths_cannot_escape(self):
        for value in ['../../etc','/a/../b','/a;whoami','/a\ncommand']:
            with self.assertRaises(ValueError):agent.project_path(value)

    def test_model_cannot_invent_dockerfile(self):
        with self.assertRaises(ValueError):agent.validate_plan({'build_pack':'dockerfile','port':8000},[])

    def test_database_and_missing_secrets_block_deploy(self):
        for extra in [{'databases':['SQLite volume']},{'missing_env':['API_KEY']}]:
            p=agent.validate_plan({'build_pack':'nixpacks','port':8000,'ready':True,**extra},[])
            self.assertFalse(p['ready'])

    def test_port_is_bounded(self):
        for port in [0,65536,True,'8000']:
            with self.assertRaises(ValueError):agent.validate_plan({'build_pack':'static','port':port},[])

    def test_login_and_csrf(self):
        client=agent.app.test_client()
        self.assertEqual(client.get('/api/jobs').status_code,401)
        logged=client.post('/api/login',json={'email':cfg['email'],'password':'test-password'})
        self.assertEqual(logged.status_code,200)
        self.assertIn('HttpOnly',logged.headers['Set-Cookie'])
        self.assertEqual(client.post('/api/analyze',json={}).status_code,403)
        self.assertEqual(client.post('/api/analyze',json={'repository':'file:///etc/passwd'},
            headers={'X-CSRF-Token':logged.json['csrf']}).status_code,400)

    def check_archive_rejected(self,name,kind=tarfile.REGTYPE,size=3,content=b'abc',message=None):
        data=io.BytesIO()
        with tarfile.open(fileobj=data,mode='w:gz') as t:
            m=tarfile.TarInfo(name);m.type=kind;m.size=size
            if kind==tarfile.SYMTYPE:m.linkname='/etc/passwd';m.size=0
            t.addfile(m,io.BytesIO(content) if kind==tarfile.REGTYPE and size==len(content) else None)
        job={'id':'a'*24,'repository':'https://github.com/test/example','commit':'b'*40,'tree_sha':'c'*40}
        with patch.object(agent.urllib.request,'urlopen',return_value=io.BytesIO(data.getvalue())):
            with self.assertRaisesRegex(ValueError,message or '.*'):agent.stage_snapshot(job)
        self.assertFalse((agent.STATE/'repos'/('a'*24+'.git')).exists())

    def test_archive_path_traversal(self):self.check_archive_rejected('root/../../escaped')
    def test_archive_symlinks(self):self.check_archive_rejected('root/link',tarfile.SYMTYPE)
    def test_archive_size_limit(self):self.check_archive_rejected('root/huge',size=256*1024*1024+1)
    def test_source_tree_must_match_upstream(self):self.check_archive_rejected('root/index.html')

    def test_lfs_pointer_is_not_treated_as_source(self):
        pointer=b'version https://git-lfs.github.com/spec/v1\noid sha256:abc\nsize 100\n'
        self.check_archive_rejected('root/media.bin',size=len(pointer),content=pointer,message='Git LFS')

    def test_retry_does_not_poll_old_failed_deployment(self):
        job={'id':'d'*24,'status':'failed','plan':{'ready':True},'deployment_uuid':'old-failed-id'}
        agent.save(job)
        client=agent.app.test_client()
        logged=client.post('/api/login',json={'email':cfg['email'],'password':'test-password'})
        with patch.object(agent.pool,'submit'):
            result=client.post('/api/jobs/'+job['id']+'/deploy',json={},
                headers={'X-CSRF-Token':logged.json['csrf']})
        self.assertEqual(result.status_code,202)
        self.assertNotIn('deployment_uuid',agent.load(job['id']))


if __name__=='__main__':unittest.main()
