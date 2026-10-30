"""Model adapters. Mock is a deterministic simulator, never real-model evidence."""

import copy
import json
import os
import urllib.error
import urllib.request


class ModelError(Exception):
    pass


def action(name, arguments, reason):
    return {"action": name, "arguments": arguments, "reason": reason}


class HTTPModel:
    mode = "live"

    def __init__(self, timeout=45):
        self.key = os.environ.get("OPENAI_API_KEY", "")
        self.name = os.environ.get("OPENAI_MODEL", "")
        self.base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        self.timeout = timeout
        if not self.key or not self.name:
            raise ModelError("请配置 OPENAI_API_KEY 和 OPENAI_MODEL；离线运行可选择 --model mock")
        if not self.base.startswith("https://") and not self.base.startswith(("http://localhost:", "http://127.0.0.1:")):
            raise ModelError("模型地址须为 HTTPS，或本地 HTTP 地址")

    def choose(self, context, history, definitions):
        messages = [{"role": "system", "content": context["system"]},
                    {"role": "user", "content": json.dumps(context["input"], ensure_ascii=False)}]
        for index, record in enumerate(history):
            selected = record["decision"]
            call_id = f"call_{index}"
            messages.append({"role": "assistant", "tool_calls": [{
                "id": call_id, "type": "function", "function": {
                    "name": selected["action"],
                    "arguments": json.dumps({"arguments": selected["arguments"], "reason": selected["reason"]}, ensure_ascii=False),
                }}]})
            messages.append({"role": "tool", "tool_call_id": call_id,
                             "content": json.dumps(record["observation"], ensure_ascii=False)})
        body = {"model": self.name, "messages": messages, "tools": definitions,
                "tool_choice": "required", "parallel_tool_calls": False}
        request = urllib.request.Request(self.base + "/chat/completions", data=json.dumps(body).encode(),
                                         headers={"Authorization": "Bearer " + self.key, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.load(response)
            calls = payload["choices"][0]["message"].get("tool_calls")
            if not calls:
                raise ModelError("模型未返回工具动作")
            if len(calls) != 1:
                raise ModelError("模型返回多个动作，不符合串行协议")
            function = calls[0]["function"]
            args = json.loads(function["arguments"])
            return action(function["name"], args["arguments"], args["reason"])
        except urllib.error.HTTPError as exc:
            # Do not expose server bodies, authorization headers or credentials.
            raise ModelError(f"模型 HTTP 请求失败，状态码 {exc.code}") from None
        except urllib.error.URLError:
            raise ModelError("模型网络连接失败（请检查 DNS、网络或 TLS）") from None
        except OSError:
            raise ModelError("模型请求超时或连接中断") from None
        except (ValueError, KeyError, IndexError, TypeError):
            raise ModelError("模型响应 JSON 或动作参数格式无效") from None


class MockModel:
    mode = "mock"
    name = "deterministic-offline-simulator"

    def __init__(self, scenario="normal"):
        self.scenario = scenario

    def choose(self, context, history, definitions):
        request = context["input"]
        missing = [key for key in ("topic", "audience", "platform", "target_duration_seconds", "style")
                   if request.get(key) is None or isinstance(request.get(key), str) and not request[key].strip()]
        if missing:
            return action("finish", {"status": "needs_input", "message": "请补充关键信息", "questions": ["请提供 " + ", ".join(missing)]}, "输入字段不完整")
        if self.scenario == "limit":
            return action("search_materials", {"query": "不存在的素材"}, "离线上限测试，持续检索")
        if not history:
            return action("search_materials", {"query": request["topic"]}, "先检索事实来源")
        last = history[-1]
        observation = last["observation"]
        if not observation["ok"]:
            if observation.get("error", {}).get("retryable"):
                return copy.deepcopy(last["decision"])
            return action("finish", {"status": "tool_error", "message": "工具无法继续", "questions": []}, "观察到不可恢复错误")
        result = observation["result"]
        if last["decision"]["action"] == "search_materials":
            if not result["matches"]:
                attempts = sum(h["decision"]["action"] == "search_materials" for h in history)
                if attempts < 2:
                    return action("search_materials", {"query": request["topic"] + " 产品资料"}, "首次无命中，改写查询")
                return action("finish", {"status": "insufficient_material", "message": "未找到支持主题的产品资料", "questions": []}, "改写查询后仍无素材")
            material = result["matches"][0]
            fact = material["facts"][0]
            scenes = [{"id": "S01", "visual": "产品画面", "voiceover": fact["text"], "subtitle": fact["text"],
                       "claims": [{"text": fact["text"], "source_id": material["id"], "fact_id": fact["id"]}]}]
            if self.scenario == "duration_revision":
                scenes[0]["voiceover"] = "字幕" * 80
            return action("estimate_duration", {"script": {"version": 1, "title": "字幕功能介绍", "scenes": scenes},
                                                "target_duration_seconds": request["target_duration_seconds"]}, "生成离线测试草稿后估时")
        if last["decision"]["action"] == "estimate_duration":
            script = copy.deepcopy(last["decision"]["arguments"]["script"])
            if result["status"] == "failed":
                if script["version"] >= 2:
                    return action("finish", {"status": "constraints_unsatisfied", "message": "压缩后仍无法满足时长", "questions": []}, "观察到第二版仍超限")
                script["version"] += 1
                script["scenes"][0]["voiceover"] = script["scenes"][0]["claims"][0]["text"]
                return action("estimate_duration", {"script": script, "target_duration_seconds": request["target_duration_seconds"]}, "根据超时反馈压缩并重新估时")
            return action("check_rules", {"script": script}, "时长通过，检查事实和品牌规则")
        if result.get("facts") == "passed" and result.get("brand") == "passed":
            return action("finish", {"status": "completed", "message": "脚本已通过检查", "questions": []}, "当前版本检查均已通过")
        return action("finish", {"status": "constraints_unsatisfied", "message": "脚本规则检查未通过", "questions": []}, "仍有未解决规则问题")
