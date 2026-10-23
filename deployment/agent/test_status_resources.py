"""Regression cases for hidden replies, truthful progress and host resource access."""
import json
from pathlib import Path
from unittest.mock import patch
import unittest
import test_conversation

class StatusResourceTests(unittest.TestCase):
    setUp=test_conversation.ConversationTests.setUp
    post=test_conversation.ConversationTests.post
    def test_status_question_answers_immediately_even_while_model_busy(self):
        from test_guards import agent
        agent.save({**self.job,'status':'deploying','progress':{'phase':'pull','text':'拉取镜像中','updated_at':1}})
        agent.chat_pending.add(self.job['id'])
        with patch.object(agent.chat_pool,'submit') as model:
            self.assertEqual(self.post('/chat',{'message':'部署完了吗？'}).status_code,202)
            model.assert_not_called()
        last=agent.read_conversation(self.job['id'])['messages'][-1]['content']
        self.assertIn('尚未完成',last);self.assertIn('90 秒',last)

    def test_deployed_answer_is_grounded_in_verified_result(self):
        from test_guards import agent
        agent.save({**self.job,'status':'deployed','deployed_commit':'a'*40,'verification':'首页可访问'})
        self.post('/chat',{'message':'部署完了吗？'})
        text=agent.read_conversation(self.job['id'])['messages'][-1]['content']
        self.assertIn('本次部署已完成',text);self.assertIn('aaaaaaaaaaaa',text)

    def test_progress_has_independent_activity_and_poll_times(self):
        from test_guards import agent
        job={**self.job,'status':'deploying','deployment_uuid':'test'};agent.save(job)
        with patch.object(agent,'coolify',return_value={'status':'in_progress','logs':[{'output':'Pulling image'}]}):
            with patch.object(agent.time,'time',return_value=100):agent.sync_deployment(job)
            with patch.object(agent.time,'time',return_value=200):agent.sync_deployment(job)
        live=agent.read_conversation(job['id'])['live_build']
        self.assertEqual(live['updated_at'],100);self.assertEqual(live['checked_at'],200)
        self.assertEqual(agent.load(job['id'])['progress']['phase'],'pull')

    def test_engine_milestone_does_not_mark_deployed(self):
        from test_guards import agent
        job={**self.job,'status':'deploying','deployment_uuid':'test'};agent.save(job)
        with patch.object(agent,'coolify',return_value={'status':'in_progress','logs':[{'output':'Rolling update completed'}]}):agent.sync_deployment(job)
        self.assertEqual(agent.load(job['id'])['status'],'deploying')
        self.assertEqual(agent.load(job['id'])['progress']['phase'],'preview')

    def test_restart_marks_pending_reply_interrupted(self):
        from test_guards import agent
        data=agent.read_conversation(self.job['id']);data['chat_request']={'status':'pending','started_at':1};agent.write_conversation(self.job['id'],data)
        agent.recover_interrupted();agent.recover_interrupted()
        messages=agent.read_conversation(self.job['id'])['messages']
        self.assertEqual(sum('中断了上一条' in m['content'] for m in messages),1)

    def test_resources_require_auth_and_report_unavailable_or_stale(self):
        from test_guards import agent
        self.assertEqual(agent.app.test_client().get('/api/resources').status_code,401)
        path=agent.STATE/'resource-fixture'
        with patch.object(agent,'RESOURCE_FILE',path):
            self.assertEqual(self.client.get('/api/resources').status_code,503)
            path.write_text(json.dumps({'sampled_at':1,'disk':{'used':123}}))
            r=self.client.get('/api/resources')
            self.assertTrue(r.json['stale']);self.assertEqual(r.json['disk']['used'],123)
            self.assertEqual(r.headers['Cache-Control'],'no-store')
