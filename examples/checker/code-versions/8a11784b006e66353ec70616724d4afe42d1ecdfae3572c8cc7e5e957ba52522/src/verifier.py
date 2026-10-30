"""Semantic claim review: a model judges every sentence, the program validates the verdicts.

The lexical scan in ``check_rules`` only catches wording it has seen before.  This
layer asks a judge model to list every statement about the product in each
sentence and say whether a retrieved fact directly supports it.  The program does
not trust the judge blindly: every segment must come back exactly once, a
"supported" verdict must name existing fact IDs, and those facts must be cited in
the same scene.  Anything else is reported as an issue.
"""

from __future__ import annotations

import json
import re

SEGMENT_SPLIT = r"[。！？!?；;\n]+"

JUDGE_INSTRUCTIONS = """你是短视频脚本的产品事实核查员，只做判定，不改写文案。

输入包含 facts（素材中允许使用的产品事实原文）和 segments（脚本中逐句拆出的文本）。
对每个 segment，找出其中所有“产品声明”，并判断是否被 facts 直接支持。

产品声明：任何关于产品或其功能的陈述，包括
- 能做什么、怎么操作、有哪些选项/样式/数量/语言；
- 使用后带来的结果或效果（省时、播放量、完播率、观众体验、专业感、上手难度等）；
- 适合谁、适用什么场景、与其他产品或旧做法的比较；
- 隐含表达也算，例如“这款工具剪片子快多了”是效率声明，“一键出成片”是操作与能力声明。
不是产品声明：创作者自身的习惯、经历或感受；不指向产品的拍摄建议；向观众提问、互动收尾；
对画面的中性描述（人物、纸卡、提纲、镜头运动）；不依赖产品的一般常识。

supported：只有当某条 fact 原文直接、完整地表达了该声明，不需要推理、引申或补充细节时才成立。
一条“支持某功能”的事实只证明“支持该功能”本身，不证明该功能如何实现、是否自动、有多少选项、
能带来什么效果或适合什么人。否定或改变事实含义的说法（如“不支持……”）判 unsupported。
无法确定时判 unsupported。

输出要求：每个 segment 按原 id 返回一次；没有产品声明时 claims 为空数组。
fact_ids 只能填写输入中存在的 fact_id；unsupported 时 fact_ids 为空数组。reason 用一句中文说明。"""

VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "segments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "claims": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "text": {"type": "string"},
                                "verdict": {"type": "string", "enum": ["supported", "unsupported"]},
                                "fact_ids": {"type": "array", "items": {"type": "string"}},
                                "reason": {"type": "string"},
                            },
                            "required": ["text", "verdict", "fact_ids", "reason"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["id", "claims"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["segments"],
    "additionalProperties": False,
}


class JudgeError(Exception):
    """The judge could not return a usable verdict; never treated as a pass."""


def split_segments(script):
    """Title and every visible scene field, split into sentences."""
    segments = []

    def add(location, scene_id, text, cited):
        for sentence in re.split(SEGMENT_SPLIT, text):
            if sentence.strip():
                segments.append({
                    "id": f"G{len(segments) + 1:02}", "location": location,
                    "scene_id": scene_id, "text": sentence.strip(),
                    "cited_fact_ids": sorted(cited),
                })

    all_cited = {claim["fact_id"] for scene in script["scenes"] for claim in scene["claims"]}
    add("title", None, script["title"], all_cited)
    for scene in script["scenes"]:
        cited = {claim["fact_id"] for claim in scene["claims"]}
        for key in ("visual", "voiceover", "subtitle"):
            add(f"{scene['id']}.{key}", scene["id"], scene[key], cited)
    return segments


def review(script, facts, judge):
    """Run the judge and validate its verdicts against facts and citations.

    ``facts`` maps (source_id, fact_id) to fact text.  Raises JudgeError when the
    judge fails or returns an incomplete verdict, so the caller can surface a
    retryable tool error instead of a pass.
    """
    segments = split_segments(script)
    known_fact_ids = {fact_id for _, fact_id in facts}
    payload = {
        "facts": [{"source_id": s, "fact_id": f, "text": t} for (s, f), t in sorted(facts.items())],
        "segments": [{"id": seg["id"], "location": seg["location"], "text": seg["text"]} for seg in segments],
    }
    verdict = judge.judge(payload)
    returned = verdict.get("segments") if isinstance(verdict, dict) else None
    if not isinstance(returned, list):
        raise JudgeError("语义复核结果缺少 segments")
    by_id = {}
    for item in returned:
        if not isinstance(item, dict) or not isinstance(item.get("claims"), list):
            raise JudgeError("语义复核结果格式无效")
        if item.get("id") in by_id:
            raise JudgeError("语义复核结果包含重复句段")
        by_id[item.get("id")] = item
    if set(by_id) != {seg["id"] for seg in segments}:
        raise JudgeError("语义复核结果未覆盖全部句段")

    issues, reviewed = [], []
    for seg in segments:
        for claim in by_id[seg["id"]]["claims"]:
            if not isinstance(claim, dict) or claim.get("verdict") not in ("supported", "unsupported"):
                raise JudgeError("语义复核声明格式无效")
            fact_ids = claim.get("fact_ids") or []
            record = {"location": seg["location"], "segment": seg["text"],
                      "claim": str(claim.get("text", "")), "verdict": claim["verdict"],
                      "fact_ids": list(fact_ids), "reason": str(claim.get("reason", ""))}
            reviewed.append(record)
            if claim["verdict"] == "unsupported":
                issues.append({"rule_id": "SEM01", "location": seg["location"], "text": seg["text"],
                               "reason": "语义复核：产品声明缺少素材支持——" + record["reason"]})
            elif not fact_ids or not set(fact_ids) <= known_fact_ids:
                # The judge named no fact or an invented one: do not accept the pass.
                issues.append({"rule_id": "SEM02", "location": seg["location"], "text": seg["text"],
                               "reason": "语义复核判为受支持，但未给出存在的事实 ID"})
            elif not set(fact_ids) <= set(seg["cited_fact_ids"]):
                issues.append({"rule_id": "SEM03", "location": seg["location"], "text": seg["text"],
                               "reason": "该产品声明需在本分镜 claims 中引用 " + "、".join(fact_ids)})
    return {
        "status": "failed" if issues else "passed",
        "judge": getattr(judge, "name", "unknown"), "judge_mode": getattr(judge, "mode", "unknown"),
        "segments_reviewed": len(segments), "claims": reviewed, "issues": issues,
    }


class OfflineJudge:
    """Deterministic stand-in for tests and Mock runs; it does NOT judge meaning.

    Sentences listed in ``annotations`` get the given claims; every other sentence
    is reported as having no product claim.  It only exercises the flow.
    """

    mode = "offline"
    name = "offline-fixture-judge"

    def __init__(self, annotations=None):
        self.annotations = dict(annotations or {})

    def judge(self, payload):
        return {"segments": [
            {"id": seg["id"], "claims": list(self.annotations.get(seg["text"], []))}
            for seg in payload["segments"]
        ]}


class LLMJudge:
    """Judge backed by the configured OpenAI-compatible model (structured output)."""

    mode = "live"

    def __init__(self, client, model=None):
        # ``client`` is an HTTPModel: reuse its key, base URL, timeout and API choice.
        self.client = client
        self.model = model or client.name
        self.name = self.model

    def judge(self, payload):
        from .models import ModelError  # local import avoids a models <-> tools cycle

        content = json.dumps(payload, ensure_ascii=False)
        try:
            if self.client.api == "responses":
                body = {
                    "model": self.model, "instructions": JUDGE_INSTRUCTIONS, "store": False,
                    "input": [{"role": "user", "content": content}],
                    "text": {"format": {"type": "json_schema", "name": "claim_verdicts",
                                        "schema": VERDICT_SCHEMA, "strict": True}},
                }
                if self.client.reasoning_effort:
                    body["reasoning"] = {"effort": self.client.reasoning_effort}
                response = self.client._post("/responses", body)
                text = "".join(
                    part.get("text", "")
                    for item in response.get("output", []) if item.get("type") == "message"
                    for part in item.get("content", []) if part.get("type") == "output_text"
                )
            else:
                body = {
                    "model": self.model,
                    "messages": [{"role": "system", "content": JUDGE_INSTRUCTIONS},
                                 {"role": "user", "content": content}],
                    "response_format": {"type": "json_schema", "json_schema": {
                        "name": "claim_verdicts", "schema": VERDICT_SCHEMA, "strict": True}},
                }
                response = self.client._post("/chat/completions", body)
                text = response["choices"][0]["message"]["content"] or ""
            return json.loads(text)
        except ModelError as exc:
            raise JudgeError(f"语义复核模型调用失败：{exc}") from None
        except (ValueError, KeyError, IndexError, TypeError, AttributeError):
            raise JudgeError("语义复核模型返回的 JSON 无效") from None
