"""Input, action and tool contracts, independent of runtime state."""

import copy
import json
import re

from .tools.local import ROOT, positive_number

FIELDS = ("topic", "audience", "platform", "target_duration_seconds", "style")
LABELS = {"topic": "主题", "audience": "受众", "platform": "平台",
          "target_duration_seconds": "目标时长", "style": "风格"}
STATUSES = {"completed", "needs_input", "insufficient_material", "tool_error", "constraints_unsatisfied"}


def validate_input(value):
    if not isinstance(value, dict) or set(value) - set(FIELDS):
        raise ValueError("输入须为对象且只能包含约定的五个字段")
    for key, item in value.items():
        if item is None:
            continue
        if key == "target_duration_seconds":
            if not positive_number(item):
                raise ValueError("target_duration_seconds 须为有限正数")
        elif not isinstance(item, str):
            raise ValueError(f"{key} 须为字符串或 null")


def missing_fields(request):
    return [key for key in FIELDS if request.get(key) is None or
            isinstance(request.get(key), str) and not request[key].strip()]


def validate_decision(decision):
    if not isinstance(decision, dict) or set(decision) != {"action", "arguments", "reason"}:
        raise ValueError("模型动作须包含 action、arguments、reason")
    if not isinstance(decision["action"], str) or not isinstance(decision["arguments"], dict):
        raise ValueError("动作名须为字符串，参数须为对象")
    if not isinstance(decision["reason"], str) or not decision["reason"].strip():
        raise ValueError("须有简短公开决策依据")


def validate_finish_arguments(args, missing):
    if set(args) != {"status", "message", "questions"}:
        raise ValueError("finish 参数字段无效")
    if not isinstance(args["status"], str) or args["status"] not in STATUSES:
        raise ValueError("finish 状态无效")
    if not isinstance(args["message"], str) or not args["message"].strip():
        raise ValueError("finish 须有结果说明")
    questions = args["questions"]
    if not isinstance(questions, list) or not all(isinstance(q, str) and q.strip() for q in questions):
        raise ValueError("questions 须为非空问句的数组")
    for question in questions:
        if question.strip() in FIELDS or not re.search(r"[？?]|请|能否|多少|什么|是否|哪", question):
            raise ValueError("questions 必须是用户可理解的提问，例如‘请问目标时长是多少秒？’，不能只返回字段名")
    if args["status"] == "needs_input":
        if not questions:
            raise ValueError("请求补充时必须给出问题")
        for field in missing:
            if not any(LABELS[field] in q for q in questions):
                raise ValueError(f"请用中文明确询问缺失的{LABELS[field]}")


def object_schema(properties):
    return {
        "type": "object", "properties": properties,
        "required": list(properties), "additionalProperties": False,
    }


def make_strict(schema):
    if isinstance(schema, dict):
        if schema.get("type") == "object":
            schema["required"] = list(schema.get("properties", {}))
            schema["additionalProperties"] = False
        for value in schema.values():
            make_strict(value)
    elif isinstance(schema, list):
        for value in schema:
            make_strict(value)


def definitions():
    contract = json.loads((ROOT / "schemas/output.schema.json").read_text())
    scene_schema = copy.deepcopy(contract["$defs"]["scene"])
    scene_schema["required"].remove("estimated_duration_seconds")
    scene_schema["properties"].pop("estimated_duration_seconds")
    # Runtime validates nonempty voiceover or subtitle.
    scene_schema.pop("anyOf", None)
    scene_schema["properties"]["claims"]["items"] = contract["$defs"]["claim"]
    script_schema = copy.deepcopy(contract["$defs"]["script"])
    script_schema["required"].remove("estimated_total_duration_seconds")
    script_schema["properties"].pop("estimated_total_duration_seconds")
    script_schema["properties"]["scenes"]["items"] = scene_schema
    arguments = {
        "search_materials": object_schema({
            "query": {"type": "string"}, "limit": {"type": "integer"},
        }),
        "estimate_duration": object_schema({
            "script": script_schema, "target_duration_seconds": {"type": "number"},
        }),
        "check_rules": object_schema({"script": script_schema}),
        "finish": object_schema({
            "status": {"enum": sorted(STATUSES)}, "message": {"type": "string"},
            "questions": {"type": "array", "items": {"type": "string"}},
        }),
    }
    descriptions = {
        "search_materials": "检索本地产品素材，返回来源 ID 和允许使用的事实；无命中时返回空数组。",
        "estimate_duration": "计算草稿每镜和总时长，检查目标三分之二至目标的区间，并返回过长或过短方向。",
        "check_rules": "检查产品声明与引用是否一致；词法扫描能力、效果及品牌风险，并由判定模型逐句复核所有产品声明是否有素材支持。",
        "finish": "请求补充、说明失败或提交当前草稿；完成要求当前版本所有检查通过。",
    }
    tools = []
    for name, schema in arguments.items():
        make_strict(schema)
        tools.append({
            "type": "function",
            "function": {
                "name": name, "strict": True,
                "description": descriptions[name] + "只给一句公开依据，不提供内部思维过程。",
                "parameters": object_schema({
                    "reason": {"type": "string"}, "arguments": schema,
                }),
            },
        })
    return tools
