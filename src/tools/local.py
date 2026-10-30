"""Local tools with JSON-serializable results and explicit failure envelopes."""

import hashlib
import json
import math
import re
from decimal import Decimal, ROUND_CEILING
from pathlib import Path

from ..verifier import JudgeError, review


ROOT = Path(__file__).resolve().parents[2]


class DataError(Exception):
    """Unreadable or structurally invalid local tool data."""


def fingerprint(script):
    payload = json.dumps(script, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def positive_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0


def validate_script(script):
    if not isinstance(script, dict):
        raise ValueError("script 必须为对象")
    if set(script) - {"version", "title", "scenes", "estimated_total_duration_seconds"}:
        raise ValueError("script 含未知字段")
    version = script.get("version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise ValueError("version 必须为正整数")
    if not isinstance(script.get("title"), str) or not script["title"].strip():
        raise ValueError("title 不能为空")
    scenes = script.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        raise ValueError("scenes 必须为非空数组")
    ids = set()
    for scene in scenes:
        if not isinstance(scene, dict):
            raise ValueError("分镜必须为对象")
        if set(scene) - {"id", "visual", "voiceover", "subtitle", "claims", "estimated_duration_seconds"}:
            raise ValueError("分镜含未知字段")
        sid = scene.get("id")
        if not isinstance(sid, str) or not sid.strip() or sid in ids:
            raise ValueError("分镜 id 必须非空且唯一")
        ids.add(sid)
        for field in ("visual", "voiceover", "subtitle"):
            if not isinstance(scene.get(field), str):
                raise ValueError(f"{sid}.{field} 必须为字符串")
        if not scene["visual"].strip() or not (scene["voiceover"].strip() or scene["subtitle"].strip()):
            raise ValueError(f"{sid} 须有画面和至少一项旁白或字幕")
        if not isinstance(scene.get("claims"), list):
            raise ValueError(f"{sid}.claims 必须为数组")
        for claim in scene["claims"]:
            if not isinstance(claim, dict) or any(
                not isinstance(claim.get(key), str) or not claim[key].strip()
                for key in ("text", "source_id", "fact_id")
            ):
                raise ValueError(f"{sid} 的 claim 格式无效")
            if set(claim) != {"text", "source_id", "fact_id"}:
                raise ValueError(f"{sid} 的 claim 含未知字段")


def compact(text):
    return re.sub(r"[\W_]+", "", text, flags=re.UNICODE).casefold()


class ToolSet:
    def __init__(self, data_dir=None, failures=None, judge=None):
        self.data_dir = Path(data_dir) if data_dir else ROOT / "data"
        # Semantic claim judge used by check_rules; None means the layer is not configured.
        self.judge = judge
        # Test-only fault injection: remaining failures for each tool.
        self.failures = dict(failures or {})

    def execute(self, name, arguments):
        """Single dispatch boundary; failures are observations, never passed checks."""
        methods = {
            "search_materials": self.search_materials,
            "estimate_duration": self.estimate_duration,
            "check_rules": self.check_rules,
        }
        if name not in methods:
            return self._error(name, "UNKNOWN_TOOL", "未知工具", False)
        if not isinstance(arguments, dict):
            return self._error(name, "INVALID_ARGUMENTS", "参数必须为对象", False)
        if self.failures.get(name, 0) > 0:
            self.failures[name] -= 1
            return self._error(name, "INJECTED_FAILURE", "测试注入的临时工具错误", True)
        try:
            return {"ok": True, "tool": name, "result": methods[name](**arguments)}
        except DataError:
            return self._error(name, "DATA_UNAVAILABLE", "本地数据不可读取或格式无效", False)
        except JudgeError as exc:
            # A judge outage is a failed check, never a pass; it may be transient.
            return self._error(name, "JUDGE_UNAVAILABLE", str(exc), True)
        except (ValueError, TypeError) as exc:
            return self._error(name, "INVALID_ARGUMENTS", str(exc), False)
        except OSError:
            return self._error(name, "DATA_UNAVAILABLE", "本地数据不可读取", False)

    @staticmethod
    def _error(name, code, message, retryable):
        return {"ok": False, "tool": name, "error": {"code": code, "message": message, "retryable": retryable}}

    def _load(self, filename):
        try:
            data = json.loads((self.data_dir / filename).read_text(encoding="utf-8"))
            if filename == "materials.json":
                if not isinstance(data["materials"], list):
                    raise ValueError("materials must be a list")
                for material in data["materials"]:
                    if not all(isinstance(material[key], str) and material[key].strip() for key in ("id", "title")):
                        raise ValueError("invalid material")
                    if not isinstance(material["keywords"], list) or not all(isinstance(t, str) for t in material["keywords"]):
                        raise ValueError("invalid keywords")
                    if not isinstance(material["facts"], list):
                        raise ValueError("invalid facts")
                    for fact in material["facts"]:
                        if not all(isinstance(fact[key], str) and fact[key].strip() for key in ("id", "text")):
                            raise ValueError("invalid fact")
                ids = [m["id"] for m in data["materials"]]
                if len(ids) != len(set(ids)):
                    raise ValueError("duplicate source IDs")
                for material in data["materials"]:
                    ids = [f["id"] for f in material["facts"]]
                    if len(ids) != len(set(ids)):
                        raise ValueError("duplicate fact IDs")
            else:
                segments = data["claim_policy"]["signal_patterns"]
                if not isinstance(segments, list) or not all(isinstance(t, str) for t in segments):
                    raise ValueError("invalid signal patterns")
                for pattern in segments:
                    re.compile(pattern)
                re.compile(data["claim_policy"]["negation_pattern"])
                if not isinstance(data["rules"], list):
                    raise ValueError("invalid rules")
                for rule in data["rules"]:
                    if not isinstance(rule["id"], str):
                        raise ValueError("invalid rule ID")
                    examples = rule.get("violation_examples", [])
                    if not isinstance(examples, list) or not all(isinstance(t, str) and compact(t) for t in examples):
                        raise ValueError("invalid violation examples")
            return data
        except (OSError, ValueError, TypeError, KeyError, re.error) as exc:
            raise DataError from exc

    def search_materials(self, query, limit=5):
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query 必须为非空字符串")
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 20:
            raise ValueError("limit 必须为 1–20 的整数")
        q = compact(query)
        if not q:
            raise ValueError("query 必须包含文字或数字")
        matches = []
        for material in self._load("materials.json")["materials"]:
            terms = [material["id"], material["title"], *material["keywords"]]
            score = sum(bool(compact(term)) and (compact(term) in q or q in compact(term)) for term in terms)
            if score:
                matches.append({**material, "score": score})
        matches.sort(key=lambda item: (-item["score"], item["id"]))
        return {"query": query, "matches": matches[:limit], "total_matches": len(matches), "method": "normalized_substring"}

    def estimate_duration(self, script, target_duration_seconds):
        validate_script(script)
        if not positive_number(target_duration_seconds):
            raise ValueError("target_duration_seconds 必须为有限正数")
        scenes = []
        total = Decimal("0")
        for scene in script["scenes"]:
            # Spoken/read units: each CJK character, each Latin word, each digit.
            def units(text):
                return len(re.findall(r"[\u3400-\u9fff]|[A-Za-z]+|\d|[^\W\d_A-Za-z\u3400-\u9fff]", text))

            spoken = units(scene["voiceover"])
            subtitle = units(scene["subtitle"])
            duration = max(Decimal(spoken) / 4, Decimal(subtitle) / 5, Decimal("1")) + Decimal("0.5")
            duration = duration.quantize(Decimal("0.1"), rounding=ROUND_CEILING)
            total += duration
            scenes.append({"id": scene["id"], "voiceover_units": spoken, "subtitle_units": subtitle, "estimated_duration_seconds": float(duration)})
        maximum = Decimal(str(target_duration_seconds))
        minimum = (maximum * Decimal(2) / Decimal(3)).quantize(Decimal("0.1"), rounding=ROUND_CEILING)
        passed = minimum <= total <= maximum
        direction = "within_range" if passed else "too_long" if total > maximum else "too_short"
        return {
            "script_version": script["version"], "script_hash": fingerprint(script),
            "scenes": scenes, "estimated_total_duration_seconds": float(total),
            "target_duration_seconds": target_duration_seconds,
            "status": "passed" if passed else "failed",
            "minimum_duration_seconds": float(minimum),
            "direction": direction,
            "under_by_seconds": float(max(Decimal("0"), minimum - total)),
            "over_by_seconds": float(max(Decimal("0"), total - Decimal(str(target_duration_seconds)))),
            "method": "max(旁白单位/4, 字幕单位/5, 1秒画面下限) + 每镜0.5秒停顿；每镜向上取一位小数后求和",
            "limitations": ["启发式估算，不能替代实际配音与剪辑；不采信输入中的预计时长。"],
        }

    def check_rules(self, script):
        validate_script(script)
        materials = self._load("materials.json")["materials"]
        rules = self._load("brand_rules.json")
        facts = {
            (material["id"], fact["id"]): fact["text"]
            for material in materials for fact in material["facts"]
        }
        issues = []
        valid_refs = set()

        def issue(rule, location, text, reason):
            issues.append({"rule_id": rule, "location": location,
                           "text": text, "reason": reason})

        for scene in script["scenes"]:
            visible = [compact(scene[key]) for key in ("visual", "voiceover", "subtitle")]
            for claim in scene["claims"]:
                ref = (claim["source_id"], claim["fact_id"])
                if ref not in facts:
                    issue("BR05", scene["id"], claim["text"], "素材或事实 ID 不存在")
                elif compact(claim["text"]) != compact(facts[ref]):
                    issue("BR01", scene["id"], claim["text"], "产品声明必须逐字对应素材事实，不得扩写")
                elif not any(compact(claim["text"]) in text for text in visible):
                    issue("BR05", scene["id"], claim["text"], "引用声明未出现在该分镜正文中")
                else:
                    valid_refs.add((scene["id"], ref))

        fields = [("title", script["title"], None)]
        for scene in script["scenes"]:
            fields.extend(
                (f"{scene['id']}.{key}", scene[key], scene["id"])
                for key in ("visual", "voiceover", "subtitle")
            )
        policy = rules["claim_policy"]
        signals = re.compile("|".join(policy["signal_patterns"]), re.IGNORECASE)
        for location, text, sid in fields:
            for rule in rules["rules"]:
                for example in rule.get("violation_examples", []):
                    if compact(example) in compact(text):
                        issue(rule["id"], location, example, "命中当前品牌规则禁止示例")
            for segment in re.split(r"[。！？!?；;\n]+", text):
                remaining = compact(segment)
                if not remaining:
                    continue
                for ref, fact in facts.items():
                    normalized_fact = compact(fact)
                    if normalized_fact not in remaining:
                        continue
                    has_reference = any(
                        valid_ref == ref and (sid is None or scene_id == sid)
                        for scene_id, valid_ref in valid_refs
                    )
                    if not has_reference:
                        issue("BR05", location, segment, "产品事实缺少本分镜有效引用；标题需在分镜中引用")
                        continue
                    # An affirmative fact cannot substantiate a negated sentence.
                    before_fact = remaining.split(normalized_fact, 1)[0]
                    if re.search(policy["negation_pattern"], before_fact):
                        issue("BR01", location, segment, "否定表述与引用事实不一致")
                    remaining = remaining.replace(normalized_fact, "")
                if signals.search(remaining):
                    issue("BR01S", location, segment,
                          "未被引用事实覆盖的文字含能力、效果、数字或宣传信号，需证据或改写")
        lexical_failed = any(item["rule_id"] in ("BR01", "BR01S", "BR02", "BR03", "BR05") for item in issues)
        brand_failed = any(item["rule_id"] in ("BR02", "BR03", "BR04") for item in issues)
        signals_found = [item for item in issues if item["rule_id"] == "BR01S"]
        if self.judge is None:
            # No judge: open-ended risk signals block on their own (fail closed).
            semantic = {"status": "not_configured", "issues": [], "claims": []}
        else:
            # With a judge, signal hits are hints; the semantic verdict decides those sentences.
            # Banned examples, citation integrity, verbatim claims and negation still block.
            semantic = review(script, facts, self.judge)
            issues = [item for item in issues if item["rule_id"] != "BR01S"]
        issues.extend(semantic["issues"])
        facts_failed = semantic["status"] == "failed" or any(
            item["rule_id"] in ("BR01", "BR01S", "BR02", "BR03", "BR05") for item in issues)
        return {
            "script_version": script["version"], "script_hash": fingerprint(script),
            "facts": "failed" if facts_failed else "passed",
            "brand": "failed" if brand_failed else "passed",
            "lexical": "failed" if lexical_failed else "passed",
            "semantic": {key: value for key, value in semantic.items() if key != "issues"},
            "signals": signals_found if self.judge is not None else [],
            "issues": issues, "mode": "claims_risk_signals_and_semantic_review",
            "limitations": rules["limitations"] + [
                "语义复核依赖判定模型，可能误判；未配置判定模型时只有词法层，Agent 不允许完成。"],
        }
