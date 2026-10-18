"""IP testing retains the same login and HTTPS boundaries as public domains."""
import unittest
from unittest.mock import patch
from test_guards import agent, cfg

class IPTests(unittest.TestCase):
    def test_ip_requires_activation_https_and_authentication(self):
        client=agent.app.test_client();base='https://'+agent.publication.TEMP_IP
        with patch.object(agent.publication,'ip_enabled',return_value=False):
            self.assertEqual(client.get('/',base_url=base).status_code,503)
        with patch.object(agent.publication,'ip_enabled',return_value=True):
            self.assertEqual(client.get('/api/jobs',base_url=base).status_code,401)
            response=client.post('/api/login',base_url=base,json={'email':cfg['email'],'password':'test-password'})
            self.assertEqual(response.status_code,200)
            self.assertIn('; Secure;',response.headers['Set-Cookie'])
            self.assertEqual(client.post('/api/analyze',base_url=base,json={}).status_code,403)
            self.assertEqual(client.get('/',base_url='http://'+agent.publication.TEMP_IP).status_code,403)

    def test_only_exact_challenge_path_bypasses_gate(self):
        client=agent.access.auth_app.test_client()
        host=agent.publication.TEMP_IP
        with patch.object(agent.publication,'ip_enabled',return_value=False):
            for path,expected in [('/.well-known/acme-challenge/abc_DEF-12',200),
                                  ('/.well-known/acme-challenge/../api/jobs',503),
                                  ('/api/jobs',503),('/',503)]:
                self.assertEqual(client.get('/check',headers={'X-Forwarded-Host':host,'X-Forwarded-Uri':path,'X-Forwarded-Proto':'http'}).status_code,expected)

    def test_ip_redirects_before_authentication(self):
        with patch.object(agent.publication,'ip_enabled',return_value=True):
            response=agent.access.auth_app.test_client().get('/check',headers={
                'X-Forwarded-Host':agent.publication.TEMP_IP,'X-Forwarded-Proto':'http'})
            self.assertEqual(response.status_code,308)
            self.assertEqual(response.headers['Location'],'https://'+agent.publication.TEMP_IP+'/')

if __name__=='__main__':unittest.main()
