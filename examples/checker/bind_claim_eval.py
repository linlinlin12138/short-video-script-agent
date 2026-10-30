"""Bind an existing evaluation to a retrospective, immutable source snapshot.

This records evidence after execution; it is not a claim of run-start attestation.
Run once: python3 -m examples.checker.bind_claim_eval
"""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
FOLDER = ROOT / "examples/checker"


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def version_id(files):
    return sha256(json.dumps(files, sort_keys=True, separators=(",", ":")).encode())


def main():
    target = FOLDER / "claim-eval-live.runtime-manifest.json"
    if target.exists():
        raise SystemExit("Manifest already exists; verify it instead of overwriting evidence.")
    report_path = FOLDER / "claim-eval-live.json"
    report = json.loads(report_path.read_text())
    paths = [p for group in ("src", "data", "schemas")
             for p in (ROOT / group).rglob("*")
             if p.is_file() and p.suffix in (".py", ".json")]
    paths += [ROOT / name for name in (
        "requirements.txt", "examples/checker/run_claim_eval.py",
        "examples/checker/run_regression.py") if (ROOT / name).exists()]
    contents = {p.relative_to(ROOT).as_posix(): p.read_bytes() for p in sorted(paths)}
    files = {name: sha256(content) for name, content in contents.items()}
    code_version = version_id(files)
    snapshot = FOLDER / "code-versions" / code_version
    for name, content in contents.items():
        dest = snapshot / name
        if dest.exists() and dest.read_bytes() != content:
            raise SystemExit(f"Snapshot conflict: {name}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)
    prior_path = ROOT / "examples/live/normal/runtime-manifest.json"
    prior = json.loads(prior_path.read_text())
    shared = sorted(set(prior) & set(files))
    mismatches = [name for name in shared if prior[name] != files[name]]
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    dirty = bool(subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=ROOT, text=True).strip())
    artifacts = {p.relative_to(ROOT).as_posix(): sha256(p.read_bytes()) for p in (
        report_path, FOLDER / "claim-eval-live.trace.jsonl",
        FOLDER / "claim-eval-live.verification.json")}
    manifest = {
        "schema_version": 1,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "capture_mode": "retrospective_not_run_start_attestation",
        "provenance": "Snapshot captured after evaluation. No runtime source, dataset, rules, or evaluation runner changes were made between this run and capture in this work session. Hashes cannot independently prove historical execution. Future Git commits must not be presented as the original run commit.",
        "code_version_sha256": code_version,
        "snapshot": snapshot.relative_to(ROOT).as_posix(),
        "files": files,
        "git_context_at_capture": {"head": head, "dirty": dirty,
                                   "head_is_exact_run_version": False},
        "run": {key: report[key] for key in (
            "started_at", "finished_at", "judge", "judge_mode", "api",
            "reasoning_effort", "rules_version", "dataset_sha256")},
        "command": "python3 -m examples.checker.run_claim_eval --judge live --env-file .env --api responses --reasoning-effort medium --timeout 60",
        "artifacts": artifacts,
        "prior_runtime_crosscheck": {
            "path": prior_path.relative_to(ROOT).as_posix(),
            "sha256": sha256(prior_path.read_bytes()),
            "shared_files": shared, "mismatches": mismatches,
        },
    }
    target.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(f"Bound code version: {code_version}")
    print(f"Prior runtime comparison: {len(shared)} files; mismatches={mismatches}")


if __name__ == "__main__":
    main()
