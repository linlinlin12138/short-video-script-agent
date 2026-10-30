"""Measure claim detection on the labelled set, per layer and per split.

Offline (no model calls, lexical layer only):
    python3 -m examples.checker.run_claim_eval
With the real judge model (one model call per sentence):
    python3 -m examples.checker.run_claim_eval --judge live --env-file .env
"""

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from src.cli import load_env
from src.models import HTTPModel
from src.tools import ToolSet
from src.tools.local import ROOT
from src.verifier import LLMJudge
from examples.checker.run_regression import script_with_claim


def summarize(records, layer):
    summary = {}
    for split in sorted({r["split"] for r in records}):
        for label in ("unsupported", "no_claim", "supported"):
            rows = [r for r in records if r["split"] == split and r["label"] == label]
            if not rows:
                continue
            outcomes = [r[layer] for r in rows]
            correct = sum(o == ("flagged" if label == "unsupported" else "passed") for o in outcomes)
            summary[f"{split}/{label}"] = {
                "expected": "flagged" if label == "unsupported" else "passed",
                "correct": correct, "total": len(rows), "errors": outcomes.count("error"),
            }
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--judge", choices=("none", "live"), default="none")
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--api", choices=("responses", "chat"), default="responses")
    parser.add_argument("--reasoning-effort", choices=("none", "low", "medium", "high"))
    parser.add_argument("--timeout", type=float, default=60)
    args = parser.parse_args(argv)
    if args.env_file:
        load_env(args.env_file)
    judge = None
    if args.judge == "live":
        import os
        judge = LLMJudge(HTTPModel(args.timeout, args.reasoning_effort, args.api),
                         os.environ.get("OPENAI_JUDGE_MODEL") or None)
    dataset_path = ROOT / "data/eval/claim_eval.json"
    dataset = json.loads(dataset_path.read_text())
    started_at = datetime.now(timezone.utc).isoformat()
    name = "claim-eval-live.json" if judge else "claim-eval-lexical.json"
    target = Path(__file__).with_name(name)
    trace_path = target.with_suffix(".trace.jsonl")
    trace_path.write_text("")
    tools = ToolSet(judge=judge)
    records = []
    for index, item in enumerate(dataset["items"], 1):
        arguments = {"script": script_with_claim(item["text"])}
        output = tools.execute("check_rules", arguments)
        with trace_path.open("a") as trace:
            trace.write(json.dumps({"index": index, "item": item, "tool": "check_rules",
                                    "arguments": arguments, "output": output,
                                    "recorded_at": datetime.now(timezone.utc).isoformat()},
                                   ensure_ascii=False) + "\n")
        record = dict(item)
        if not output["ok"]:
            record.update(lexical="error", semantic="error", final="error", error=output["error"])
        else:
            result = output["result"]
            here = [i for i in result["issues"] + result["signals"] if i["location"] == "S01.voiceover"]

            def outcome(rule_prefixes, layer_status):
                if layer_status == "not_configured":
                    return "not_run"
                return "flagged" if any(i["rule_id"].startswith(rule_prefixes) for i in here) else (
                    "passed" if layer_status == "passed" else "flagged_elsewhere")

            record["lexical"] = outcome(("BR",), result["lexical"])
            record["semantic"] = outcome(("SEM",), result["semantic"]["status"])
            # final: what check_rules actually decided (signals are hints once a judge exists).
            blocking_here = [i for i in result["issues"] if i["location"] == "S01.voiceover"]
            record["final"] = "flagged" if blocking_here else (
                "passed" if result["facts"] == "passed" else "flagged_elsewhere")
            record["semantic_claims"] = result["semantic"].get("claims", [])
        records.append(record)
        print(f"[{index}/{len(dataset['items'])}] {item['split']}/{item['label']} "
              f"semantic={record['semantic']} final={record['final']}", flush=True)
    layers = ["lexical"] + (["semantic", "final"] if judge else [])
    report = {
        "judge": judge.name if judge else None,
        "judge_mode": "live" if judge else "not_configured",
        "api": args.api if judge else None,
        "reasoning_effort": args.reasoning_effort,
        "started_at": started_at,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "dataset_sha256": hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
        "trace": trace_path.relative_to(ROOT).as_posix(),
        "rules_version": json.loads((ROOT / "data/brand_rules.json").read_text())["rules_version"],
        "note": "lexical 为词法层单独判断（含风险信号）；semantic 为判定模型；final 为 check_rules 的实际结论：配置判定模型后风险信号只作提示。flagged_elsewhere 表示该句被放行但同一脚本其他位置被拦截，对 no_claim/supported 算误拦。",
        "summary": {layer: summarize(records, layer) for layer in layers},
        "records": records,
    }
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    for layer in layers:
        print(f"[{layer}]")
        for key, row in report["summary"][layer].items():
            print(f"  {key:22} {row['correct']}/{row['total']} 符合预期（应 {row['expected']}，错误 {row['errors']}）")
    print(f"已写入 {target.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
