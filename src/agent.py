"""Bounded model/tool loop with explicit state and completion guards."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
import hashlib

from .contracts import (
    definitions, missing_fields, validate_decision,
    validate_finish_arguments, validate_input,
)
from .models import ModelError
from .prompts import PROMPT_VERSION, build_context
from .tools import ToolSet
from .tools.local import DataError, fingerprint, validate_script
from .verifier import OfflineJudge

CHECK_TOOLS = {"estimate_duration", "check_rules"}


def error_observation(message):
    return {"ok": False, "error": {
        "code": "GUARD_REJECTED", "message": message, "retryable": False,
    }}


@dataclass
class RunState:
    request: dict
    missing: list
    script: dict | None = None
    checks: dict = field(default_factory=dict)
    failed_checks: set = field(default_factory=set)
    retrieved: set = field(default_factory=set)
    tool_calls: int = 0
    revision_count: int = 0

    def prepare_check(self, name, args):
        candidate = args.get("script")
        validate_script(candidate)
        changed = self.script is None or fingerprint(candidate) != fingerprint(self.script)
        if changed and self.script is not None:
            if candidate["version"] <= self.script["version"]:
                raise ValueError("修改脚本必须递增版本号")
            self.revision_count += 1
        if changed:
            self.script = copy.deepcopy(candidate)
            self.checks.clear()
            self.failed_checks.clear()
        # Failed rechecks must never reuse an earlier success.
        self.checks.pop(name, None)
        self.failed_checks.discard(name)
        if name == "estimate_duration":
            if args.get("target_duration_seconds") != self.request["target_duration_seconds"]:
                raise ValueError("估时目标必须与用户输入一致")

    def observe(self, name, observation):
        if not observation["ok"]:
            if name in CHECK_TOOLS:
                self.failed_checks.add(name)
            return
        result = observation["result"]
        if name == "search_materials":
            self.retrieved.update(
                (material["id"], fact["id"])
                for material in result["matches"] for fact in material["facts"]
            )
        elif name in CHECK_TOOLS:
            self.checks[name] = result

    def validate_finish(self, args):
        validate_finish_arguments(args, self.missing)
        duration = self.checks.get("estimate_duration", {})
        repairable_first_failure = (
            args["status"] == "constraints_unsatisfied"
            and duration.get("status") == "failed"
            and self.request.get("target_duration_seconds", 0) >= 1.5
            and self.revision_count == 0
        )
        if repairable_first_failure:
            raise ValueError("尚未尝试修正，不能直接断言无法满足；请根据实际检查反馈重新评估")
        if args["status"] != "completed":
            return
        if self.missing or not self.script or set(self.checks) != CHECK_TOOLS:
            pending = sorted(CHECK_TOOLS - set(self.checks))
            raise ValueError("尚无完整输入或最终版本检查；当前版本缺少：" + "、".join(pending))
        rules = self.checks["check_rules"]
        if duration["status"] != "passed" or any(rules[key] != "passed" for key in ("facts", "brand")):
            raise ValueError("当前版本检查未通过")
        if rules.get("semantic", {}).get("status") != "passed":
            raise ValueError("当前版本的产品声明语义复核未通过或未执行，不能完成")
        current_hash = fingerprint(self.script)
        if any(result["script_hash"] != current_hash for result in self.checks.values()):
            raise ValueError("检查未绑定当前草稿")
        claims = [claim for scene in self.script["scenes"] for claim in scene["claims"]]
        if not claims or any((c["source_id"], c["fact_id"]) not in self.retrieved for c in claims):
            raise ValueError("产品事实必须引用本次检索实际返回的资料")

    def render_result(self, status, message, mode, questions=None, judge_mode=None):
        duration = self.checks.get("estimate_duration")
        rules = self.checks.get("check_rules")
        rendered = copy.deepcopy(self.script) if duration else None
        if rendered:
            for scene, timing in zip(rendered["scenes"], duration["scenes"]):
                scene["estimated_duration_seconds"] = timing["estimated_duration_seconds"]
            rendered["estimated_total_duration_seconds"] = duration["estimated_total_duration_seconds"]
        issues = copy.deepcopy(rules["issues"]) if rules else []
        if duration and duration["status"] == "failed":
            issues.append({
                "rule_id": "DURATION", "location": "script",
                "text": str(duration["estimated_total_duration_seconds"]),
                "reason": "预计时长不在目标三分之二至目标的区间内：" + duration["direction"],
            })
        source_ids = sorted({
            claim["source_id"] for scene in rendered["scenes"] for claim in scene["claims"]
        }) if rendered else []

        def check_status(tool, key):
            if tool in self.checks:
                return self.checks[tool][key]
            return "error" if tool in self.failed_checks else "not_run"

        def semantic_status():
            if "check_rules" in self.checks:
                value = self.checks["check_rules"].get("semantic", {}).get("status", "not_run")
                return "not_run" if value == "not_configured" else value
            return "error" if "check_rules" in self.failed_checks else "not_run"

        risks = ["时长为启发式估算，未经实际配音验证。",
                 "产品声明经词法扫描与模型语义复核，两者都可能误判；发布前仍需人工逐句核对。"]
        if judge_mode == "offline":
            risks.append("本次语义复核使用离线固定标注，不代表真实语义判定。")
        if mode == "mock":
            risks.append("离线 Mock 仅验证流程，不证明真实模型决策效果。")
        return {
            "status": status, "message": message, "missing_fields": self.missing,
            "questions": questions or [], "script": rendered, "source_ids": source_ids,
            "checks": {
                "script_version": self.script["version"] if self.script else None,
                "duration": check_status("estimate_duration", "status"),
                "facts": check_status("check_rules", "facts"),
                "brand": check_status("check_rules", "brand"),
                "semantic": semantic_status(), "issues": issues,
            },
            "risks": risks, "tool_calls_used": self.tool_calls,
        }


class Agent:
    def __init__(self, model, tools=None, max_tools=10, max_rounds=12):
        if not 1 <= max_tools <= 10 or not 1 <= max_rounds <= 12:
            raise ValueError("工具上限为 1–10，模型轮数上限为 1–12")
        self.model = model
        # Default offline judge only exercises the flow; the CLI injects a real one for live runs.
        self.tools = tools or ToolSet(judge=OfflineJudge())
        self.max_tools = max_tools
        self.max_rounds = max_rounds

    def _execute(self, state, name, args):
        state.tool_calls += 1
        if state.missing:
            raise ValueError("业务信息不足，请使用 finish 请求补充")
        if name in CHECK_TOOLS:
            state.prepare_check(name, args)
        observation = self.tools.execute(name, args)
        state.observe(name, observation)
        observation["current_state"] = {
            "script_version": state.script["version"] if state.script else None,
            "completed_checks": sorted(state.checks),
            "pending_checks": sorted(CHECK_TOOLS - set(state.checks)),
        }
        return observation

    def run(self, request):
        validate_input(request)
        state = RunState(request, missing_fields(request))
        try:
            policy = self.tools._load("brand_rules.json")
        except DataError:
            policy = {"error": "品牌规则不可用，不得完成任务"}
        context = build_context(request, state.missing, policy)
        history = []
        trace = [{
            "event": "run_start", "mode": self.model.mode, "model": self.model.name,
            "input": request, "max_tools": self.max_tools, "max_rounds": self.max_rounds,
            "prompt_version": PROMPT_VERSION, "rules_version": policy.get("rules_version"),
            "reasoning_effort": getattr(self.model, "reasoning_effort", None),
            "api": getattr(self.model, "api", None),
            "prompt_hash": hashlib.sha256(context["system"].encode()).hexdigest(),
            "judge": getattr(getattr(self.tools, "judge", None), "name", None),
        }]

        def finish(status, message, questions=None):
            judge = getattr(self.tools, "judge", None)
            result = state.render_result(status, message, self.model.mode, questions,
                                         getattr(judge, "mode", None))
            trace.append({"event": "task_end", "status": status,
                          "tool_calls_used": state.tool_calls})
            return result, trace

        for step in range(1, self.max_rounds + 1):
            try:
                decision = self.model.choose(context, copy.deepcopy(history), definitions())
            except ModelError as exc:
                trace.append({"event": "model_error", "step": step, "message": str(exc)})
                return finish("tool_error", str(exc))
            try:
                validate_decision(decision)
            except ValueError as exc:
                return finish("tool_error", str(exc))
            name, args = decision["action"], decision["arguments"]
            if trace[-1].get("event") == "decision":
                trace[-1].update(next_action=name, next_action_reason=decision["reason"])
            try:
                if name == "finish":
                    state.validate_finish(args)
                    observation = {"ok": True, "result": {"accepted": True}}
                elif state.tool_calls >= self.max_tools:
                    trace.append({"event": "decision", "step": step, **decision,
                                  "observation": {"ok": False, "error": {
                                      "code": "STEP_LIMIT", "message": "工具预算耗尽，动作未执行", "retryable": False}}})
                    return finish("step_limit_reached", "工具调用次数已达上限，任务未完成")
                else:
                    observation = self._execute(state, name, args)
            except (ValueError, TypeError) as exc:
                observation = error_observation(str(exc))
            trace.append({"event": "decision", "step": step, **decision,
                          "observation": observation})
            if name == "finish" and observation["ok"]:
                return finish(args["status"], args["message"], args["questions"])
            history.append({"decision": copy.deepcopy(decision),
                            "observation": copy.deepcopy(observation)})
        return finish("step_limit_reached", "模型决策轮数已达上限，任务未完成")
