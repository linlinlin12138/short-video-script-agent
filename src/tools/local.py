"""Local tools with JSON-serializable results and explicit failure envelopes."""

import hashlib
import json
import math
import re
from decimal import Decimal, ROUND_CEILING
from pathlib import Path


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
    def __init__(self, data_dir=None, failures=None):
        self.data_dir = Path(data_dir) if data_dir else ROOT / "data"
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
                segments = data["controlled_language"]["neutral_segments"]
                if not isinstance(segments, list) or not all(isinstance(t, str) for t in segments):
                    raise ValueError("invalid neutral segments")
                if not isinstance(data["rules"], list):
                    raise ValueError("invalid rules")
                for rule in data["rules"]:
                    if not isinstance(rule["id"], str):
                        raise ValueError("invalid rule ID")
                    examples = rule.get("violation_examples", [])
                    if not isinstance(examples, list) or not all(isinstance(t, str) and compact(t) for t in examples):
                        raise ValueError("invalid violation examples")
            return data
        except (OSError, ValueError, TypeError, KeyError) as exc:
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
        passed = total <= Decimal(str(target_duration_seconds))
        return {
            "script_version": script["version"], "script_hash": fingerprint(script),
            "scenes": scenes, "estimated_total_duration_seconds": float(total),
            "target_duration_seconds": target_duration_seconds,
            "status": "passed" if passed else "failed",
            "over_by_seconds": float(max(Decimal("0"), total - Decimal(str(target_duration_seconds)))),
            "method": "max(旁白单位/4, 字幕单位/5, 1秒画面下限) + 每镜0.5秒停顿；每镜向上取一位小数后求和",
            "limitations": ["启发式估算，不能替代实际配音与剪辑；不采信输入中的预计时长。"],
        }

    def check_rules(self, script):
        validate_script(script)
        materials = self._load("materials.json")["materials"]
        rules = self._load("brand_rules.json")
        policy = rules["controlled_language"]
        facts = {(m["id"], f["id"]): f["text"] for m in materials for f in m["facts"]}
        issues = []
        valid_refs = set()

        def issue(rule, location, text, reason):
            issues.append({"rule_id": rule, "location": location, "text": text, "reason": reason})

        for scene in script["scenes"]:
            visible = "。".join(scene[field] for field in ("visual", "voiceover", "subtitle"))
            for claim in scene["claims"]:
                ref = (claim["source_id"], claim["fact_id"])
                if ref not in facts:
                    issue("BR05", scene["id"], claim["text"], "素材或事实 ID 不存在")
                elif compact(claim["text"]) != compact(facts[ref]):
                    issue("BR01", scene["id"], claim["text"], "受控模式要求声明原文与资料事实一致")
                elif compact(claim["text"]) not in compact(visible):
                    issue("BR05", scene["id"], claim["text"], "引用声明未出现在该分镜正文中")
                else:
                    valid_refs.add((scene["id"], ref))

        fields = [("title", script["title"], None)]
        for scene in script["scenes"]:
            fields.extend((f"{scene['id']}.{key}", scene[key], scene["id"]) for key in ("visual", "voiceover", "subtitle"))
        neutral = {compact(text) for text in policy["neutral_segments"]}
        for location, text, sid in fields:
            for rule in rules["rules"]:
                for example in rule.get("violation_examples", []):
                    if compact(example) in compact(text):
                        issue(rule["id"], location, example, "命中当前合成品牌规则禁止示例")
            # Fail closed: unrecognized prose is unresolved, not semantically verified.
            for segment in re.split(r"[。！？!?；;\n]+", text):
                normalized = compact(segment)
                if not normalized or normalized in neutral:
                    continue
                refs = [ref for ref, fact in facts.items() if compact(fact) == normalized]
                if not refs:
                    issue("BR01", location, segment, "不在受控事实或中性表达清单内，需改写或补充资料；不代表已证明为假")
                elif not any(ref in refs and (sid is None or sid == scene_id) for scene_id, ref in valid_refs):
                    issue("BR05", location, segment, "该事实缺少有效分镜引用；标题引用须在分镜中提供")
        facts_failed = any(item["rule_id"] in ("BR01", "BR02", "BR03", "BR05") for item in issues)
        brand_failed = any(item["rule_id"] in ("BR02", "BR03", "BR04") for item in issues)
        return {
            "script_version": script["version"], "script_hash": fingerprint(script),
            "facts": "failed" if facts_failed else "passed",
            "brand": "failed" if brand_failed else "passed",
            "issues": issues, "mode": "controlled_language",
            "limitations": ["只核验受控事实原文与中性表达清单；清单外表达保守拒绝，不提供通用语义事实判断。"],
        }
