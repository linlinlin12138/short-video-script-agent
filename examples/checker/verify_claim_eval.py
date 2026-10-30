"""Offline verification of live evaluation, source snapshot and artifact binding."""

import argparse
import json
from pathlib import Path

from examples.checker.bind_claim_eval import ROOT, FOLDER, sha256, version_id


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify(manifest_path, check_current=True):
    manifest = json.loads(manifest_path.read_text())
    require(version_id(manifest["files"]) == manifest["code_version_sha256"],
            "Source version digest mismatch")
    snapshot = ROOT / manifest["snapshot"]
    for name, expected in manifest["files"].items():
        require(sha256((snapshot / name).read_bytes()) == expected,
                f"Snapshot changed: {name}")
        if check_current:
            require(sha256((ROOT / name).read_bytes()) == expected,
                    f"Current code differs from recorded version: {name}")
    for name, expected in manifest["artifacts"].items():
        require(sha256((ROOT / name).read_bytes()) == expected,
                f"Recorded artifact changed: {name}")
    prior = manifest["prior_runtime_crosscheck"]
    require(sha256((ROOT / prior["path"]).read_bytes()) == prior["sha256"],
            "Prior runtime manifest changed")
    prior_files = json.loads((ROOT / prior["path"]).read_text())
    shared = sorted(set(prior_files) & set(manifest["files"]))
    require(shared == prior["shared_files"], "Prior shared file list differs")
    mismatches = [name for name in shared if prior_files[name] != manifest["files"][name]]
    require(mismatches == prior["mismatches"], "Prior comparison differs")
    report = json.loads((FOLDER / "claim-eval-live.json").read_text())
    trace = [json.loads(line) for line in
             (FOLDER / "claim-eval-live.trace.jsonl").read_text().splitlines()]
    dataset_bytes = (snapshot / "data/eval/claim_eval.json").read_bytes()
    require(sha256(dataset_bytes) == report["dataset_sha256"], "Dataset differs")
    items = json.loads(dataset_bytes)["items"]
    require(len(items) == len(trace) == len(report["records"]) == 36,
            "Evaluation record count differs")
    for key, value in manifest["run"].items():
        require(report[key] == value, f"Run configuration differs: {key}")
    for index, (item, step, row) in enumerate(zip(items, trace, report["records"]), 1):
        require(step["index"] == index and step["item"] == item, "Trace order differs")
        require(all(row[key] == value for key, value in item.items()), "Report item differs")
        script = step["arguments"]["script"]
        expected_script = {
            "version": 1, "title": "字幕功能介绍",
            "scenes": [{"id": "S01", "visual": "创作者举起纸卡。",
                        "voiceover": item["text"], "subtitle": "支持字幕",
                        "claims": [{"text": "支持字幕", "source_id": "P01",
                                    "fact_id": "P01-F1"}]}],
        }
        require(script == expected_script, f"Input differs at {index}")
        require(step["tool"] == "check_rules" and step["output"]["ok"],
                f"Tool failed at {index}")
        result = step["output"]["result"]
        sem = result["semantic"]
        require(sem["judge_mode"] == "live" and sem["judge"] == report["judge"],
                f"Judge mode/model differs at {index}")
        require(sem["segments_reviewed"] == 4 and row["semantic_claims"] == sem["claims"],
                f"Semantic claims differ at {index}")
        here = [i for i in result["issues"] + result["signals"]
                if i["location"] == "S01.voiceover"]
        for layer, prefix, status in (
            ("lexical", "BR", result["lexical"]), ("semantic", "SEM", sem["status"])
        ):
            outcome = "flagged" if any(i["rule_id"].startswith(prefix) for i in here) else (
                "passed" if status == "passed" else "flagged_elsewhere")
            require(row[layer] == outcome, f"{layer} outcome differs at {index}")
        blocking = any(i["location"] == "S01.voiceover" for i in result["issues"])
        final = "flagged" if blocking else (
            "passed" if result["facts"] == "passed" else "flagged_elsewhere")
        require(row["final"] == final, f"Final outcome differs at {index}")
    for layer, summary in report["summary"].items():
        for group, counts in summary.items():
            split, label = group.split("/")
            rows = [r for r in report["records"] if r["split"] == split and r["label"] == label]
            expected = "flagged" if label == "unsupported" else "passed"
            actual = {"expected": expected, "total": len(rows),
                      "correct": sum(r[layer] == expected for r in rows),
                      "errors": sum(r[layer] == "error" for r in rows)}
            require(actual == counts, f"Summary differs: {layer}/{group}")
    return {"verified": True, "code_version_sha256": manifest["code_version_sha256"],
            "record_count": len(trace), "current_code_checked": check_current,
            "capture_mode": manifest["capture_mode"]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot-only", action="store_true",
                        help="Verify the historical snapshot without requiring current code to match.")
    args = parser.parse_args()
    result = verify(FOLDER / "claim-eval-live.runtime-manifest.json", not args.snapshot_only)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
