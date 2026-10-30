"""Run: python3 -m src.cli --input examples/inputs/normal.json --model mock."""

import argparse
import json
import os
import sys
from pathlib import Path

from .agent import Agent
from .models import HTTPModel, MockModel, ModelError
from .tools import ToolSet
from .verifier import LLMJudge, OfflineJudge


def load_env(path):
    """Load only model settings as data, without executing shell expressions."""
    allowed = {"OPENAI_API_KEY", "OPENAI_MODEL", "OPENAI_BASE_URL", "OPENAI_REASONING_EFFORT",
               "OPENAI_JUDGE_MODEL"}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        name, sep, value = line.partition("=")
        if not sep:
            raise ValueError(f"环境文件第 {number} 行格式无效")
        if name.strip() not in allowed:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(name.strip(), value)


def main(argv=None):
    parser = argparse.ArgumentParser(description="短视频脚本 Agent")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--model", choices=("mock", "live"), default="mock")
    parser.add_argument("--env-file", type=Path, help="读取指定环境文件；已有进程环境变量优先")
    parser.add_argument("--scenario", choices=("normal", "duration_revision", "limit"), default="normal", help="仅供离线 Mock 使用")
    parser.add_argument("--output-dir", type=Path, default=Path("runs/latest"))
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--max-tools", type=int, default=10)
    parser.add_argument("--max-rounds", type=int, default=12)
    parser.add_argument("--api", choices=("responses", "chat"), default="responses")
    parser.add_argument("--timeout", type=float, default=45)
    parser.add_argument("--reasoning-effort", choices=("none", "low", "medium", "high"),
                        help="可选；仅使用支持 reasoning_effort 的模型时设置")
    parser.add_argument("--fail-tool", choices=("search_materials", "estimate_duration", "check_rules"), help="测试时注入一次临时工具错误")
    args = parser.parse_args(argv)
    try:
        if args.env_file:
            load_env(args.env_file)
        if not 0 < args.timeout <= 60:
            raise ValueError("timeout 须在 0–60 秒之间")
        if args.model == "live" and args.scenario != "normal":
            raise ValueError("scenario 只用于 Mock，真实模型不预设修正路径")
        request = json.loads(args.input.read_text(encoding="utf-8"))
        model = MockModel(args.scenario) if args.model == "mock" else HTTPModel(args.timeout, args.reasoning_effort, args.api)
        # Live runs judge claims with a real model (OPENAI_JUDGE_MODEL, default: same model).
        judge = OfflineJudge() if args.model == "mock" else LLMJudge(
            HTTPModel(args.timeout, args.reasoning_effort, args.api),
            os.environ.get("OPENAI_JUDGE_MODEL") or None)
        tools = ToolSet(data_dir=args.data_dir, failures={args.fail_tool: 1} if args.fail_tool else None,
                        judge=judge)
        result, trace = Agent(model, tools, args.max_tools, args.max_rounds).run(request)
        args.output_dir.mkdir(parents=True, exist_ok=True)
        for name, value in (("input.json", request), ("output.json", result)):
            (args.output_dir / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (args.output_dir / "trace.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in trace), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] == "completed" else 1
    except (OSError, ValueError, ModelError) as exc:
        print(f"运行配置或输入错误：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
