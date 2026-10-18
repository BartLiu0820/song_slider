"""Publication and update boundaries without public network or model calls."""
from unittest.mock import patch
import unittest
from test_guards import agent,cfg

class ReleaseTests(unittest.TestCase):
    def login(self,client,base='http://localhost'):
        return client.post('/api/login',json={'email':cfg['email'],'password':'test-password'},base_url=base)

    def test_public_login_disabled_before_activation(self):
        client=agent.app.test_client()
        with patch.object(agent.publication,'enabled',return_value=False):
            self.assertEqual(self.login(client,'https://deploy.greatsong.online').status_code,503)

    def test_secure_public_cookie_and_local_cookie(self):
        with patch.object(agent.publication,'enabled',return_value=True):
            public=agent.app.test_client()
            response=self.login(public,'https://deploy.greatsong.online')
            self.assertEqual(response.status_code,200)
            self.assertIn('; Secure;',response.headers['Set-Cookie'])
            self.assertEqual(self.login(agent.app.test_client(),'http://deploy.greatsong.online').status_code,403)
        local=self.login(agent.app.test_client())
        self.assertEqual(local.status_code,200)
        self.assertNotIn('; Secure;',local.headers['Set-Cookie'])

    def test_untrusted_forwarded_proto_does_not_enable_http_login(self):
        client=agent.app.test_client()
        with patch.object(agent.publication,'enabled',return_value=True):
            response=client.post('/api/login',base_url='http://deploy.greatsong.online',
                headers={'X-Forwarded-Proto':'https'},json={},environ_overrides={'REMOTE_ADDR':'203.0.113.1'})
            self.assertEqual(response.status_code,403)

    def test_update_keeps_identity_and_access_but_discards_old_plan(self):
        client=agent.app.test_client();login=self.login(client)
        job={'id':'b'*24,'slug':'update-example','application_uuid':'same-application','status':'deployed',
             'commit':'a'*40,'tree_sha':'c'*40,'plan':{'ready':True},'deployment_uuid':'previous'}
        agent.save(job)
        with patch.object(agent.pool,'submit'):
            response=client.post('/api/jobs/'+job['id']+'/refresh',json={},headers={'X-CSRF-Token':login.json['csrf']})
        self.assertEqual(response.status_code,202)
        updated=agent.load(job['id'])
        self.assertEqual(updated['application_uuid'],job['application_uuid'])
        self.assertEqual(updated['deployed_commit'],job['commit'])
        self.assertNotIn('plan',updated)
        self.assertNotIn('deployment_uuid',updated)
        self.assertEqual(client.post('/api/jobs/'+job['id']+'/refresh',json={},headers={'X-CSRF-Token':login.json['csrf']}).status_code,409)

    def test_unknown_host_rejected(self):
        self.assertEqual(agent.app.test_client().get('/',base_url='http://attacker.example').status_code,400)

    def test_logs_require_admin(self):
        self.assertEqual(agent.app.test_client().get('/api/jobs/'+'a'*24+'/logs').status_code,401)

if __name__=='__main__':unittest.main()
