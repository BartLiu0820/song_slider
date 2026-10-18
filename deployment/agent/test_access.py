"""Access policy tests, isolated from live deployment state."""
import base64
import json
import os
from pathlib import Path
import tempfile
import unittest

TEMP = tempfile.TemporaryDirectory()
os.environ['SONG_STATE'] = TEMP.name
import access
access.ROOT = Path(TEMP.name)
access.DIRECTORY = access.ROOT / 'security'

class AccessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.job = {'id':'a'*24,'slug':'example'}
        (access.ROOT / (cls.job['id']+'.json')).write_text(json.dumps(cls.job))
        access.create_account('allowed','testing-password-123')
        access.create_account('outsider','testing-password-456')

    def setUp(self):
        access.failures.clear()
        self.client=access.auth_app.test_client()
        access.set_policy(self.job['id'],{'mode':'restricted','accounts':['allowed']})

    def get(self,user=None,password='testing-password-123',host='example.localhost:19180',path='/'):
        headers={'X-Forwarded-Host':host,'X-Forwarded-Uri':path,'X-Forwarded-For':'127.0.0.1'}
        if user:headers['Authorization']='Basic '+base64.b64encode((user+':'+password).encode()).decode()
        return self.client.get('/check',headers=headers)

    def test_no_credentials_and_all_assets_blocked(self):
        for path in ['/','/styles/style.css','/api/data','/socket']:
            self.assertEqual(self.get(path=path).status_code,401)

    def test_account_scope_and_domain_aliases(self):
        self.assertEqual(self.get('outsider','testing-password-456').status_code,401)
        self.assertEqual(self.get('allowed','wrong').status_code,401)
        for host in ['example.localhost:19180','example.preview.greatsong.online','EXAMPLE.LOCALHOST.']:
            r=self.get('allowed',host=host)
            self.assertEqual(r.status_code,200)
            self.assertEqual(r.headers['Authorization'],'')

    def test_public_and_existing_site(self):
        access.set_policy(self.job['id'],{'mode':'public','accounts':[]})
        self.assertEqual(self.get().status_code,200)
        for host in ['greatsong.online','www.greatsong.online','deploy.greatsong.online']:
            self.assertEqual(self.get(host=host).status_code,200)
        r=self.client.get('/check',headers={'X-Forwarded-Host':'example.localhost','Authorization':'Bearer app-token'})
        self.assertEqual(r.headers['Authorization'],'Bearer app-token')

    def test_unknown_hosts_fail_closed(self):
        self.assertEqual(self.get(host='unknown.preview.greatsong.online').status_code,403)
        self.assertEqual(self.get(host='47.116.108.184').status_code,403)

    def test_revoke_is_immediate_even_when_cached(self):
        self.assertEqual(self.get('allowed').status_code,200)
        access.set_policy(self.job['id'],{'mode':'restricted','accounts':['outsider']})
        self.assertEqual(self.get('allowed').status_code,401)

    def test_deletion_does_not_publish_and_password_not_stored(self):
        access.create_account('temporary','long-test-password')
        access.set_policy(self.job['id'],{'mode':'restricted','accounts':['temporary']})
        access.delete_account('temporary')
        self.assertEqual(access.policy(self.job['id']),{'mode':'restricted','accounts':[]})
        self.assertEqual(self.get().status_code,401)
        self.assertNotIn('testing-password', (access.DIRECTORY/'access.json').read_text())

    def test_policy_validation(self):
        for value in [{},{'mode':'all'},{'mode':'restricted','accounts':[]},{'mode':'restricted','accounts':['unknown']}]:
            with self.assertRaises(ValueError):access.set_policy(self.job['id'],value)

    def test_bruteforce_limited(self):
        for _ in range(12):self.assertEqual(self.get('allowed','wrong').status_code,401)
        self.assertEqual(self.get('allowed','wrong').status_code,429)

if __name__=='__main__':unittest.main()
