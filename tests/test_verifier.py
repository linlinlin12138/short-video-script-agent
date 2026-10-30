"""Semantic claim review: program-side validation of judge verdicts (no network)."""

import copy
import io
import json
import unittest
from unittest.mock import patch

from src.agent import Agent
from src.models import HTTPModel, MockModel
from src.tools import ToolSet
from src.verifier import JudgeError, LLMJudge, OfflineJudge, split_segments

REQUEST = {"topic": "介绍字幕功能", "audience": "创作者", "platform": "抖音",
           "target_duration_seconds": 30, "style": "简洁"}
FABRICATED = "导入视频就能出字幕"


def script(voiceover=FABRICATED, claims=True):
    return {"version": 1, "title": "字幕功能介绍", "scenes": [{
        "id": "S01", "visual": "创作者举起纸卡。", "voiceover": voiceover, "subtitle": "支持字幕",
        "claims": [{"text": "支持字幕", "source_id": "P01", "fact_id": "P01-F1"}] if claims else [],
    }]}


def unsupported(text):
    return [{"text": text, "verdict": "unsupported", "fact_ids": [], "reason": "素材未说明自动生成"}]


def supported(text, fact_ids=("P01-F1",)):
    return [{"text": text, "verdict": "supported", "fact_ids": list(fact_ids), "reason": "事实原文"}]


class BrokenJudge:
    mode, name = "live", "broken"

    def __init__(self, result=None, error=None):
        self.result, self.error = result, error

    def judge(self, payload):
        if self.error:
            raise self.error
        return copy.deepcopy(self.result)


class SemanticReviewTests(unittest.TestCase):
    def check(self, judge, draft):
        return ToolSet(judge=judge).execute("check_rules", {"script": draft})

    def test_unsupported_claim_fails_even_when_lexical_scan_passes(self):
        result = self.check(OfflineJudge({FABRICATED: unsupported(FABRICATED)}), script())["result"]
        self.assertEqual(result["lexical"], "passed")  # the lexical layer misses this sentence
        self.assertEqual(result["semantic"]["status"], "failed")
        self.assertEqual(result["facts"], "failed")
        self.assertTrue(any(i["rule_id"] == "SEM01" and i["location"] == "S01.voiceover"
                            for i in result["issues"]))

    def test_with_judge_risk_signals_are_hints_but_hard_rules_still_block(self):
        narrative = "我习惯先把文案同步到备忘录"  # lexical signal "同步", not a product claim
        result = self.check(OfflineJudge(), script(narrative))["result"]
        self.assertEqual(result["lexical"], "failed")
        self.assertEqual(result["facts"], "passed")
        self.assertTrue(any(i["rule_id"] == "BR01S" for i in result["signals"]))
        banned = self.check(OfflineJudge(), script("效率提升 80%"))["result"]
        self.assertEqual(banned["facts"], "failed")
        self.assertTrue(any(i["rule_id"] == "BR02" for i in banned["issues"]))

    def test_without_judge_risk_signals_block(self):
        result = ToolSet().execute("check_rules", {"script": script("我习惯先把文案同步到备忘录")})["result"]
        self.assertEqual(result["facts"], "failed")
        self.assertEqual(result["semantic"]["status"], "not_configured")

    def test_supported_claim_with_citation_passes(self):
        judge = OfflineJudge({"支持字幕": supported("支持字幕")})
        result = self.check(judge, script("这次只说一点：支持字幕"))["result"]
        self.assertEqual(result["semantic"]["status"], "passed")
        self.assertEqual(result["facts"], "passed")

    def test_invented_fact_id_from_judge_is_not_accepted(self):
        judge = OfflineJudge({"支持字幕": supported("支持字幕", ["P01-F9"])})
        result = self.check(judge, script("支持字幕"))["result"]
        self.assertTrue(any(i["rule_id"] == "SEM02" for i in result["issues"]))
        self.assertEqual(result["facts"], "failed")

    def test_supported_claim_must_be_cited_in_same_scene(self):
        judge = OfflineJudge({"支持字幕": supported("支持字幕")})
        draft = script("支持字幕", claims=False)
        draft["scenes"].append({"id": "S02", "visual": "纸卡", "voiceover": "支持字幕", "subtitle": "",
                                "claims": [{"text": "支持字幕", "source_id": "P01", "fact_id": "P01-F1"}]})
        result = self.check(judge, draft)["result"]
        self.assertTrue(any(i["rule_id"] == "SEM03" and i["location"].startswith("S01")
                            for i in result["issues"]))

    def test_incomplete_or_failed_judge_is_a_retryable_error_not_a_pass(self):
        for judge in (BrokenJudge(result={"segments": []}),
                      BrokenJudge(result={"oops": 1}),
                      BrokenJudge(error=JudgeError("超时"))):
            with self.subTest(judge=judge.result):
                output = self.check(judge, script())
                self.assertFalse(output["ok"])
                self.assertEqual(output["error"]["code"], "JUDGE_UNAVAILABLE")
                self.assertTrue(output["error"]["retryable"])

    def test_every_visible_sentence_is_sent_to_the_judge(self):
        draft = script("第一句。第二句！")
        texts = [seg["text"] for seg in split_segments(draft)]
        self.assertEqual(texts, ["字幕功能介绍", "创作者举起纸卡", "第一句", "第二句", "支持字幕"])

    def test_agent_cannot_complete_without_semantic_review(self):
        result, trace = Agent(MockModel(), ToolSet()).run(REQUEST)
        self.assertNotEqual(result["status"], "completed")
        self.assertTrue(any("语义复核" in row.get("observation", {}).get("error", {}).get("message", "")
                            for row in trace if row.get("event") == "decision"))

    def test_agent_does_not_complete_when_judge_flags_the_draft(self):
        flagged = "这次介绍的产品事实很简单：支持字幕"
        tools = ToolSet(judge=OfflineJudge({flagged: unsupported(flagged)}))
        result, _ = Agent(MockModel(), tools).run(REQUEST)
        self.assertEqual(result["status"], "constraints_unsatisfied")
        self.assertEqual(result["checks"]["semantic"], "failed")


class LLMJudgeTransportTests(unittest.TestCase):
    ENV = {"OPENAI_API_KEY": "test", "OPENAI_MODEL": "main-model"}
    VERDICT = {"segments": [{"id": "G01", "claims": []}]}

    def test_responses_structured_output(self):
        payload = {"output": [{"type": "reasoning"}, {"type": "message", "content": [
            {"type": "output_text", "text": json.dumps(self.VERDICT)}]}]}
        with patch.dict("os.environ", self.ENV):
            client = HTTPModel(api="responses")
            with patch.object(client, "_post", return_value=payload) as post:
                judge = LLMJudge(client, "judge-model")
                self.assertEqual(judge.judge({"facts": [], "segments": []}), self.VERDICT)
                endpoint, body = post.call_args.args
                self.assertEqual(endpoint, "/responses")
                self.assertEqual(body["model"], "judge-model")
                self.assertTrue(body["text"]["format"]["strict"])
                self.assertFalse(body["store"])

    def test_chat_structured_output_and_bad_json(self):
        good = {"choices": [{"message": {"content": json.dumps(self.VERDICT)}}]}
        bad = {"choices": [{"message": {"content": "不是JSON"}}]}
        with patch.dict("os.environ", self.ENV):
            client = HTTPModel(api="chat")
            with patch("urllib.request.urlopen", return_value=io.BytesIO(json.dumps(good).encode())) as opened:
                self.assertEqual(LLMJudge(client).judge({}), self.VERDICT)
                body = json.loads(opened.call_args.args[0].data)
                self.assertEqual(body["model"], "main-model")
                self.assertEqual(body["response_format"]["type"], "json_schema")
            with patch.object(client, "_post", return_value=bad):
                with self.assertRaises(JudgeError):
                    LLMJudge(client).judge({})


if __name__ == "__main__":
    unittest.main()
