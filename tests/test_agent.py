import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from src.agent import Agent, definitions
from src.contracts import validate_finish_arguments
from src.models import HTTPModel, MockModel, ModelError, action
from src.tools import ToolSet
from src.verifier import OfflineJudge


REQUEST = {"topic": "介绍字幕功能", "audience": "创作者", "platform": "抖音", "target_duration_seconds": 30, "style": "简洁"}


class SequenceModel:
    mode, name = "mock", "test-sequence"

    def __init__(self, decisions):
        self.decisions = iter(decisions)

    def choose(self, *args):
        return copy.deepcopy(next(self.decisions))


class AgentTests(unittest.TestCase):
    def test_normal(self):
        result, trace = Agent(MockModel()).run(REQUEST)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["tool_calls_used"], 3)
        self.assertGreaterEqual(result["script"]["estimated_total_duration_seconds"], 20)
        self.assertLessEqual(result["script"]["estimated_total_duration_seconds"], 30)
        self.assertEqual(result["source_ids"], ["P01"])
        self.assertEqual([r["action"] for r in trace if "action" in r], ["search_materials", "estimate_duration", "check_rules", "finish"])

    def test_missing_input_and_no_material(self):
        request = dict(REQUEST)
        del request["target_duration_seconds"]
        result, _ = Agent(MockModel()).run(request)
        self.assertEqual(result["status"], "needs_input")
        self.assertEqual(result["tool_calls_used"], 0)
        request = dict(REQUEST, topic="视频降噪")
        result, _ = Agent(MockModel()).run(request)
        self.assertEqual(result["status"], "insufficient_material")
        self.assertEqual(result["tool_calls_used"], 2)

    def test_duration_repair(self):
        result, trace = Agent(MockModel("duration_revision")).run(REQUEST)
        self.assertEqual(result["status"], "completed")
        estimates = [r["observation"]["result"] for r in trace if r.get("action") == "estimate_duration"]
        self.assertEqual([r["status"] for r in estimates], ["failed", "passed"])
        self.assertEqual(result["script"]["version"], 2)

    def test_unachievable_duration(self):
        result, _ = Agent(MockModel()).run(dict(REQUEST, target_duration_seconds=1))
        self.assertEqual(result["status"], "constraints_unsatisfied")

    def test_tool_failure_observed_then_recovered(self):
        result, trace = Agent(MockModel(), ToolSet(failures={"search_materials": 1}, judge=OfflineJudge())).run(REQUEST)
        self.assertEqual(result["status"], "completed")
        self.assertFalse(trace[1]["observation"]["ok"])
        self.assertEqual(result["tool_calls_used"], 4)

    def test_limits(self):
        for max_tools, max_rounds in ((2, 12), (10, 2)):
            result, _ = Agent(MockModel("limit"), max_tools=max_tools, max_rounds=max_rounds).run(REQUEST)
            self.assertEqual(result["status"], "step_limit_reached")
            self.assertEqual(result["tool_calls_used"], 2)

    def test_premature_finish_blocked(self):
        finish = action("finish", {"status": "completed", "message": "完成", "questions": []}, "测试")
        result, trace = Agent(SequenceModel([finish]), max_rounds=1).run(REQUEST)
        self.assertEqual(result["status"], "step_limit_reached")
        self.assertFalse(trace[1]["observation"]["ok"])

    def test_new_version_invalidates_old_checks(self):
        _, trace = Agent(MockModel()).run(REQUEST)
        decisions = [r for r in trace if r.get("event") == "decision"]
        actions = [{key: row[key] for key in ("action", "arguments", "reason")} for row in decisions]
        modified = copy.deepcopy(actions[2])
        modified["arguments"]["script"]["version"] = 2
        modified["arguments"]["script"]["scenes"][0]["subtitle"] = "看看你的内容提纲。"
        actions.insert(3, modified)
        result, rows = Agent(SequenceModel(actions), max_rounds=5).run(REQUEST)
        self.assertNotEqual(result["status"], "completed")
        self.assertEqual(result["checks"]["duration"], "not_run")

    def test_same_version_content_change_rejected(self):
        _, trace = Agent(MockModel()).run(REQUEST)
        decisions = [{key: row[key] for key in ("action", "arguments", "reason")} for row in trace if row.get("event") == "decision"]
        decisions[2]["arguments"]["script"]["scenes"][0]["subtitle"] = "自动生成字幕"
        result, rows = Agent(SequenceModel(decisions), max_rounds=4).run(REQUEST)
        self.assertNotEqual(result["status"], "completed")
        self.assertIn("递增版本", rows[3]["observation"]["error"]["message"])

    def test_target_tampering_rejected(self):
        _, trace = Agent(MockModel()).run(REQUEST)
        decision = copy.deepcopy(trace[2])
        selected = {key: decision[key] for key in ("action", "arguments", "reason")}
        selected["arguments"]["target_duration_seconds"] = 999
        result, rows = Agent(SequenceModel([selected]), max_rounds=1).run(REQUEST)
        self.assertIn("用户输入", rows[1]["observation"]["error"]["message"])

    def test_model_failure(self):
        model = MockModel()
        with patch.object(model, "choose", side_effect=ModelError("测试服务错误")):
            result, _ = Agent(model).run(REQUEST)
        self.assertEqual(result["status"], "tool_error")

    def test_questions_must_be_natural_language_and_cover_missing_field(self):
        for questions in (["target_duration_seconds"], ["请提供产品名称？"], []):
            with self.subTest(questions=questions), self.assertRaises(ValueError):
                validate_finish_arguments(
                    {"status": "needs_input", "message": "请补充", "questions": questions},
                    ["target_duration_seconds"],
                )
        validate_finish_arguments(
            {"status": "needs_input", "message": "请补充", "questions": ["请问目标时长是多少秒？"]},
            ["target_duration_seconds"],
        )

    def test_no_search_cannot_complete(self):
        _, trace = Agent(MockModel()).run(REQUEST)
        decisions = [{key: row[key] for key in ("action", "arguments", "reason")} for row in trace if row.get("event") == "decision"][1:]
        result, rows = Agent(SequenceModel(decisions), max_rounds=3).run(REQUEST)
        self.assertNotEqual(result["status"], "completed")
        self.assertIn("本次检索", rows[-2]["observation"]["error"]["message"])

    def test_repairable_duration_cannot_be_declared_impossible_without_attempt(self):
        _, trace = Agent(MockModel('duration_revision')).run(REQUEST)
        decisions = [{key: row[key] for key in ('action', 'arguments', 'reason')} for row in trace if row.get('event') == 'decision'][:2]
        decisions.append(action('finish', {'status': 'constraints_unsatisfied', 'message': '超时', 'questions': []}, '测试过早结束'))
        result, rows = Agent(SequenceModel(decisions), max_rounds=3).run(REQUEST)
        self.assertEqual(result['status'], 'step_limit_reached')
        self.assertIn('尚未尝试修正', rows[-2]['observation']['error']['message'])

    def test_failed_recheck_does_not_reuse_pass(self):
        _, trace = Agent(MockModel()).run(REQUEST)
        decisions = [{key: row[key] for key in ("action", "arguments", "reason")} for row in trace if row.get("event") == "decision"]
        decisions.insert(3, copy.deepcopy(decisions[2]))

        class FailSecondCheck(ToolSet):
            count = 0

            def execute(self, name, arguments):
                if name == "check_rules":
                    self.count += 1
                    if self.count == 2:
                        return self._error(name, "TEST_FAILURE", "重检失败", False)
                return super().execute(name, arguments)

        result, _ = Agent(SequenceModel(decisions), FailSecondCheck(), max_rounds=5).run(REQUEST)
        self.assertNotEqual(result["status"], "completed")
        self.assertEqual(result["checks"]["facts"], "error")

    def test_http_adapter_protocol_without_network(self):
        payload = {"choices": [{"message": {"tool_calls": [{"function": {
            "name": "search_materials", "arguments": json.dumps({"reason": "检索", "arguments": {"query": "字幕"}})
        }}]}}]}
        import io
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-secret", "OPENAI_MODEL": "test-model", "OPENAI_BASE_URL": "https://example.test/v1"}), patch("urllib.request.urlopen", return_value=io.BytesIO(json.dumps(payload).encode())) as mocked:
            selected = HTTPModel(api="chat").choose({"system": "test", "input": REQUEST}, [], definitions())
            self.assertEqual(selected["action"], "search_materials")
            body = json.loads(mocked.call_args.args[0].data)
            self.assertFalse(body["parallel_tool_calls"])
            self.assertEqual(len(body["tools"]), 4)
            self.assertTrue(all(tool['function']['strict'] for tool in body['tools']))

    def test_strict_tool_objects_have_no_optional_or_unknown_fields(self):
        def inspect(value):
            if isinstance(value, dict):
                if value.get('type') == 'object':
                    self.assertEqual(set(value['required']), set(value['properties']))
                    self.assertFalse(value['additionalProperties'])
                for child in value.values():
                    inspect(child)
            elif isinstance(value, list):
                for child in value:
                    inspect(child)
        inspect(definitions())

    def test_responses_adapter_replays_provider_items_and_actual_observation(self):
        first = {"output": [
            {"type": "reasoning", "id": "r1", "encrypted_content": "opaque-test-only", "summary": []},
            {"type": "function_call", "name": "search_materials", "call_id": "original-call",
             "arguments": json.dumps({"reason": "检索", "arguments": {"query": "字幕", "limit": 5}})},
        ]}
        second = {"output": [{
            "type": "function_call", "name": "finish", "call_id": "finish-call",
            "arguments": json.dumps({"reason": "无资料", "arguments": {
                "status": "insufficient_material", "message": "无资料", "questions": []}}),
        }]}
        context = {"system": "test", "input": REQUEST}
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test", "OPENAI_MODEL": "test"}):
            model = HTTPModel(reasoning_effort="low")
            with patch.object(model, "_post", side_effect=[first, second]) as mocked:
                chosen = model.choose(context, [], definitions())
                observation = {"ok": True, "result": {"matches": []}}
                model.choose(context, [{"decision": chosen, "observation": observation}], definitions())
                body = mocked.call_args.args[1]
                self.assertFalse(body["store"])
                self.assertEqual(body["reasoning"], {"effort": "low"})
                self.assertIn(first["output"][0], body["input"])
                self.assertEqual(body["input"][-1]["call_id"], "original-call")
                self.assertEqual(json.loads(body["input"][-1]["output"]), observation)


if __name__ == "__main__":
    unittest.main()
