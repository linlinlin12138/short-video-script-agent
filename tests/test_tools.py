import copy
import tempfile
import unittest
from pathlib import Path

from src.tools import ToolSet


def draft():
    return {
        "version": 1,
        "title": "字幕功能介绍",
        "scenes": [{
            "id": "S01", "visual": "产品画面", "voiceover": "支持字幕",
            "subtitle": "支持字幕", "estimated_duration_seconds": 999,
            "claims": [{"text": "支持字幕", "source_id": "P01", "fact_id": "P01-F1"}],
        }],
        "estimated_total_duration_seconds": 999,
    }


class ToolTests(unittest.TestCase):
    def setUp(self):
        self.tools = ToolSet()

    def call(self, name, **arguments):
        result = self.tools.execute(name, arguments)
        self.assertTrue(result["ok"], result)
        return result["result"]

    def test_search_hit_and_miss(self):
        hit = self.call("search_materials", query="介绍字幕功能")
        self.assertEqual(hit["matches"][0]["id"], "P01")
        self.assertEqual(hit["matches"][0]["facts"][0]["text"], "支持字幕")
        self.assertEqual(self.call("search_materials", query="视频降噪")["matches"], [])

    def test_duration_ignores_draft_estimates_and_simultaneous_subtitle(self):
        script = draft()
        before = copy.deepcopy(script)
        result = self.call("estimate_duration", script=script, target_duration_seconds=30)
        self.assertEqual(result["estimated_total_duration_seconds"], 1.5)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(script, before)

    def test_overlong_then_shorter_actual_estimate(self):
        script = draft()
        script["scenes"][0]["voiceover"] = "字幕" * 80
        first = self.call("estimate_duration", script=script, target_duration_seconds=30)
        self.assertEqual(first["estimated_total_duration_seconds"], 40.5)
        self.assertEqual(first["status"], "failed")
        script["version"] = 2
        script["scenes"][0]["voiceover"] = "支持字幕"
        second = self.call("estimate_duration", script=script, target_duration_seconds=30)
        self.assertEqual(second["status"], "passed")
        self.assertNotEqual(first["script_hash"], second["script_hash"])

    def test_rounding_and_sum(self):
        script = draft()
        scene = copy.deepcopy(script["scenes"][0])
        scene.update(id="S02", voiceover="一二三四五")
        script["scenes"].append(scene)
        result = self.call("estimate_duration", script=script, target_duration_seconds=3.3)
        self.assertEqual(result["estimated_total_duration_seconds"], 3.3)
        self.assertEqual(result["status"], "passed")

    def test_supported_fact_passes(self):
        result = self.call("check_rules", script=draft())
        self.assertEqual((result["facts"], result["brand"]), ("passed", "passed"))
        self.assertEqual(result["issues"], [])

    def test_fabricated_claims_in_all_fields(self):
        for field in ("title", "visual", "voiceover", "subtitle"):
            with self.subTest(field=field):
                script = draft()
                if field == "title":
                    script[field] = "效率提升 80%"
                else:
                    script["scenes"][0][field] = "自动生成字幕"
                result = self.call("check_rules", script=script)
                self.assertEqual(result["facts"], "failed")
                self.assertTrue(any(field in issue["location"] for issue in result["issues"]))

    def test_unknown_paraphrase_fails_closed(self):
        script = draft()
        script["scenes"][0]["voiceover"] = "让制作变得更轻松"
        result = self.call("check_rules", script=script)
        self.assertEqual(result["facts"], "failed")

    def test_reference_integrity(self):
        for mutation in ("missing", "wrong_id", "wrong_fact", "expanded", "absent_text"):
            with self.subTest(mutation=mutation):
                script = draft()
                claim = script["scenes"][0]["claims"][0]
                if mutation == "missing":
                    script["scenes"][0]["claims"] = []
                elif mutation == "wrong_id":
                    claim["source_id"] = "P99"
                elif mutation == "wrong_fact":
                    claim["fact_id"] = "P01-F99"
                elif mutation == "expanded":
                    claim["text"] = "支持自动字幕"
                else:
                    script["scenes"][0].update(voiceover="了解字幕功能", subtitle="")
                self.assertEqual(self.call("check_rules", script=script)["facts"], "failed")

    def test_title_fact_requires_reference(self):
        script = draft()
        script["title"] = "支持字幕"
        self.assertEqual(self.call("check_rules", script=script)["facts"], "passed")
        script["scenes"][0]["claims"] = []
        self.assertEqual(self.call("check_rules", script=script)["facts"], "failed")

    def test_fault_injection_and_recovery(self):
        tools = ToolSet(failures={"search_materials": 1})
        first = tools.execute("search_materials", {"query": "字幕"})
        self.assertFalse(first["ok"])
        self.assertTrue(first["error"]["retryable"])
        self.assertTrue(tools.execute("search_materials", {"query": "字幕"})["ok"])

    def test_missing_data_returns_error(self):
        with tempfile.TemporaryDirectory() as directory:
            result = ToolSet(data_dir=directory).execute("search_materials", {"query": "字幕"})
        self.assertEqual(result["error"]["code"], "DATA_UNAVAILABLE")

    def test_corrupt_data_returns_error(self):
        for content in ("{", '{"materials": [{}]}', '{"materials": null}'):
            with self.subTest(content=content), tempfile.TemporaryDirectory() as directory:
                Path(directory, "materials.json").write_text(content)
                result = ToolSet(data_dir=directory).execute("search_materials", {"query": "字幕"})
                self.assertEqual(result["error"]["code"], "DATA_UNAVAILABLE")

    def test_invalid_parameters_and_duplicate_scene_ids(self):
        cases = [
            ("search_materials", {"query": " "}),
            ("search_materials", {"query": "!!!"}),
            ("search_materials", {"query": "字幕", "limit": True}),
            ("estimate_duration", {"script": draft(), "target_duration_seconds": float("nan")}),
            ("estimate_duration", {"script": draft(), "target_duration_seconds": True}),
            ("check_rules", {"script": {}}),
            ("check_rules", {"script": draft(), "unknown": 1}),
        ]
        script = draft()
        script["scenes"].append(copy.deepcopy(script["scenes"][0]))
        cases.append(("check_rules", {"script": script}))
        for name, arguments in cases:
            with self.subTest(name=name, arguments=arguments):
                self.assertEqual(self.tools.execute(name, arguments)["error"]["code"], "INVALID_ARGUMENTS")
        self.assertEqual(self.tools.execute("unknown", {})["error"]["code"], "UNKNOWN_TOOL")

    def test_content_hash_changes_even_without_version_change(self):
        script = draft()
        first = self.call("check_rules", script=script)
        script["scenes"][0]["subtitle"] = "自动生成字幕"
        second = self.call("check_rules", script=script)
        self.assertNotEqual(first["script_hash"], second["script_hash"])


if __name__ == "__main__":
    unittest.main()
