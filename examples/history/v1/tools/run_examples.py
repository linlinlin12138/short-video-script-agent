"""Run from repository root: python3 -m examples.tools.run_examples."""

import json
from pathlib import Path

from src.tools import ToolSet


def main():
    tools = ToolSet()
    script = {
        "version": 1, "title": "字幕功能介绍",
        "scenes": [{
            "id": "S01", "visual": "产品画面", "voiceover": "支持字幕",
            "subtitle": "支持字幕", "estimated_duration_seconds": 1.5,
            "claims": [{"text": "支持字幕", "source_id": "P01", "fact_id": "P01-F1"}],
        }],
        "estimated_total_duration_seconds": 1.5,
    }
    calls = [
        ("search_hit", "search_materials", {"query": "介绍字幕功能"}),
        ("search_miss", "search_materials", {"query": "视频降噪"}),
        ("duration_pass", "estimate_duration", {"script": script, "target_duration_seconds": 30}),
        ("rules_pass", "check_rules", {"script": script}),
    ]
    long_script = json.loads(json.dumps(script))
    long_script["scenes"][0]["voiceover"] = "字幕" * 80
    calls.append(("duration_over_limit", "estimate_duration", {"script": long_script, "target_duration_seconds": 30}))
    bad_script = json.loads(json.dumps(script))
    bad_script["scenes"][0]["voiceover"] = "效率提升 80%"
    calls.append(("unsupported_claim", "check_rules", {"script": bad_script}))
    records = [{"case": case, "tool": name, "arguments": args, "output": tools.execute(name, args)} for case, name, args in calls]
    broken = ToolSet(failures={"search_materials": 1})
    records.append({"case": "tool_failure", "tool": "search_materials", "arguments": {"query": "字幕"}, "output": broken.execute("search_materials", {"query": "字幕"})})
    target = Path(__file__).with_name("actual-results.json")
    target.write_text(json.dumps({"kind": "actual_local_tool_runs_not_agent_trace", "records": records}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved {len(records)} local tool runs to {target}")


if __name__ == "__main__":
    main()
