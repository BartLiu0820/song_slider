import json
from pathlib import Path
import unittest
from unittest.mock import patch
from test_guards import agent

class ChatFormatTests(unittest.TestCase):
    def setUp(self):
        original=Path.read_text
        p=patch.object(Path,'read_text',lambda path,*a,**kw:'test-key' if str(path)=='/etc/song-deploy/deepseek-key' else original(path,*a,**kw));p.start();self.addCleanup(p.stop)
    def response(self,text,finish='stop'):return {'choices':[{'message':{'content':text},'finish_reason':finish}]}
    def test_invalid_json_retries_without_executing_action(self):
        bad=self.response('{"reply":"需要检查","action":refresh,"execute":False}')
        good=self.response('{"reply":"远端没有新提交","action":"none","execute":false}')
        with patch.object(agent,'call_json',side_effect=[bad,good]) as call,patch.object(agent,'submit_chat_action') as action:
            result=agent.chat_model_result([]);action.assert_not_called()
        self.assertEqual(call.call_count,2);self.assertEqual(result['reply'],'远端没有新提交')
    def test_format_failure_after_retry_has_friendly_error(self):
        with patch.object(agent,'call_json',return_value=self.response('not json')) as call:
            with self.assertRaisesRegex(ValueError,'自动纠正'):agent.chat_model_result([])
        self.assertEqual(call.call_count,2)
    def test_truncated_json_and_string_execute_are_rejected(self):
        for response in [self.response('{"reply":"ok"}','length'),self.response('{"reply":"ok","execute":"true"}')]:
            with patch.object(agent,'call_json',return_value=response):
                with self.assertRaises(ValueError):agent.chat_model_result([])
    def test_fenced_valid_object_can_be_read(self):
        with patch.object(agent,'call_json',return_value=self.response('```json\n{"reply":"ok","execute":false}\n```')):
            self.assertEqual(agent.chat_model_result([])['reply'],'ok')
    def test_remote_version_check_does_not_assume_deployed_is_latest(self):
        job={'repository':'https://github.com/example/repo','branch':'main','deployed_commit':'a'*40}
        with patch.object(agent,'call_json',return_value={'sha':'b'*40,'commit':{'message':'new'}}):
            self.assertFalse(agent.latest_source(job)['same_as_deployed'])
        with patch.object(agent,'call_json',side_effect=TimeoutError):
            self.assertIn('error',agent.latest_source(job))
