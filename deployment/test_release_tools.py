"""Offline checks for release gates and the narrowly scoped image transport shim."""
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import activate_public

spec=importlib.util.spec_from_file_location('publication_admin',Path(__file__).parent/'admin/publication_admin.py')
admin=importlib.util.module_from_spec(spec);spec.loader.exec_module(admin)

class ToolTests(unittest.TestCase):
    def test_blocked_provider_prevents_certificate_request(self):
        with patch('sys.argv',['activate_public.py']),patch.object(activate_public,'command',return_value={'hosts':['deploy.greatsong.online'],'proof':'proof'}) as command,patch.object(activate_public,'probe',return_value=(False,'blocked')):
            with self.assertRaises(SystemExit):activate_public.main()
        command.assert_called_once_with('status')

    def test_pending_routes_never_request_certificates(self):
        route=admin.routes(False,[{'id':'a'*24,'slug':'example','application_uuid':'b'*24}])
        self.assertNotIn('certResolver',json.dumps(route))
        self.assertTrue(all('https' not in r['entryPoints'] for r in route['http']['routers'].values()))

    def test_ready_routes_keep_local_docker_service_and_acme(self):
        route=admin.routes(True,[{'id':'a'*24,'slug':'example','application_uuid':'b'*24}])
        app=route['http']['routers']['song-'+'a'*24+'-tls']
        self.assertEqual(app['service'],'http-1-'+'b'*24+'@docker')
        self.assertEqual(app['tls'],{'certResolver':'letsencrypt'})

    def test_imported_dns_certificate_avoids_http_certificate_requests(self):
        route=admin.routes(True,[{'id':'a'*24,'slug':'example','application_uuid':'b'*24}],True)
        self.assertNotIn('certResolver',json.dumps(route))
        self.assertEqual(route['http']['routers']['song-workbench-https']['tls'],{})

    def shim(self,args,fail=False):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);docker=root/'docker';log=root/'calls';wrapper=root/'wrapper'
            docker.write_text("#!/usr/bin/env python3\nimport os,sys,json\nwith open(os.environ['CALLS'],'a') as f:f.write(json.dumps(sys.argv[1:])+'\\n')\nif os.environ.get('FAIL')=='1' and sys.argv[1]=='pull':sys.exit(17)\n")
            docker.chmod(0o755)
            wrapper.write_text((Path(__file__).parent/'docker-wrapper').read_text().replace('/usr/bin/docker',shlex.quote(str(docker))))
            result=subprocess.run(['sh',str(wrapper)]+args,env={**os.environ,'CALLS':str(log),'FAIL':'1' if fail else '0'})
            return result.returncode,[json.loads(line) for line in log.read_text().splitlines()]

    def test_shim_changes_only_exact_nginx_pull(self):
        code,calls=self.shim(['pull','nginx:alpine']);self.assertEqual(code,0)
        self.assertEqual(calls,[['pull','public.ecr.aws/docker/library/nginx:alpine'],['tag','public.ecr.aws/docker/library/nginx:alpine','nginx:alpine']])
        for args in [['pull','python:3.12'],['ps','--format','{{.Names}} {{.Status}}']]:
            code,calls=self.shim(args);self.assertEqual(calls,[args]);self.assertEqual(code,0)

    def test_failed_pull_never_tags_stale_image(self):
        code,calls=self.shim(['pull','nginx:alpine'],True)
        self.assertEqual(code,17);self.assertEqual(len(calls),1)

if __name__=='__main__':unittest.main()
