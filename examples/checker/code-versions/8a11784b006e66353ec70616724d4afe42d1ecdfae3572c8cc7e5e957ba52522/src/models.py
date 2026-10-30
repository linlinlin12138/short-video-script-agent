"""Model adapters. Mock is a deterministic simulator, never real-model evidence."""

import copy
import json
import os
import urllib.error
import urllib.request

from .contracts import LABELS


class ModelError(Exception):
    pass


def action(name, arguments, reason):
    return {"action": name, "arguments": arguments, "reason": reason}


class HTTPModel:
    mode = "live"

    def __init__(self, timeout=45, reasoning_effort=None, api="responses"):
        self.key = os.environ.get("OPENAI_API_KEY", "")
        self.name = os.environ.get("OPENAI_MODEL", "")
        self.base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        self.timeout = timeout
        self.reasoning_effort = reasoning_effort or os.environ.get("OPENAI_REASONING_EFFORT")
        self.api = api
        self._response_items = []
        if api not in ("chat", "responses"):
            raise ModelError("api 须为 chat 或 responses")
        if not self.key or not self.name:
            raise ModelError("请配置 OPENAI_API_KEY 和 OPENAI_MODEL；离线运行可选择 --model mock")
        if not self.base.startswith("https://") and not self.base.startswith(("http://localhost:", "http://127.0.0.1:")):
            raise ModelError("模型地址须为 HTTPS，或本地 HTTP 地址")

    def _post(self, endpoint, body):
        request = urllib.request.Request(
            self.base + endpoint, data=json.dumps(body).encode(),
            headers={"Authorization": "Bearer " + self.key, "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            raise ModelError(f"模型 HTTP 请求失败，状态码 {exc.code}") from None
        except urllib.error.URLError:
            raise ModelError("模型网络连接失败（请检查 DNS、网络或 TLS）") from None
        except OSError:
            raise ModelError("模型请求超时或连接中断") from None

    @staticmethod
    def _parse_action(name, serialized):
        args = json.loads(serialized)
        return action(name, args["arguments"], args["reason"])

    def choose(self, context, history, definitions):
        try:
            if self.api == "responses":
                return self._choose_responses(context, history, definitions)
            return self._choose_chat(context, history, definitions)
        except (ValueError, KeyError, IndexError, TypeError):
            raise ModelError("模型响应 JSON 或动作参数格式无效") from None

    def _choose_responses(self, context, history, definitions):
        if not history:
            items = [{"role": "user", "content": json.dumps(context["input"], ensure_ascii=False)}]
        else:
            # Preserve all provider output items for reasoning/tool-call continuity.
            # These items are only replayed to the same API, never included in Trace.
            items = self._response_items + [{
                "type": "function_call_output", "call_id": self._pending_call_id,
                "output": json.dumps(history[-1]["observation"], ensure_ascii=False),
            }]
        tools = [{"type": "function", **tool["function"]} for tool in definitions]
        body = {
            "model": self.name, "instructions": context["system"], "input": items,
            "tools": tools, "tool_choice": "required", "parallel_tool_calls": False,
            "store": False, "include": ["reasoning.encrypted_content"],
        }
        if self.reasoning_effort:
            body["reasoning"] = {"effort": self.reasoning_effort}
        payload = self._post("/responses", body)
        calls = [item for item in payload["output"] if item["type"] == "function_call"]
        if len(calls) != 1:
            raise ModelError("模型未返回恰好一个工具动作")
        call = calls[0]
        selected = self._parse_action(call["name"], call["arguments"])
        self._pending_call_id = call["call_id"]
        self._response_items = items + payload["output"]
        return selected

    def _choose_chat(self, context, history, definitions):
        messages = [
            {"role": "system", "content": context["system"]},
            {"role": "user", "content": json.dumps(context["input"], ensure_ascii=False)},
        ]
        for index, record in enumerate(history):
            selected = record["decision"]
            call_id = f"call_{index}"
            messages.append({"role": "assistant", "tool_calls": [{
                "id": call_id, "type": "function", "function": {
                    "name": selected["action"],
                    "arguments": json.dumps({"arguments": selected["arguments"],
                                             "reason": selected["reason"]}, ensure_ascii=False),
                }}]})
            messages.append({"role": "tool", "tool_call_id": call_id,
                             "content": json.dumps(record["observation"], ensure_ascii=False)})
        body = {"model": self.name, "messages": messages, "tools": definitions,
                "tool_choice": "required", "parallel_tool_calls": False}
        if self.reasoning_effort:
            body["reasoning_effort"] = self.reasoning_effort
        payload = self._post("/chat/completions", body)
        calls = payload["choices"][0]["message"].get("tool_calls") or []
        if len(calls) != 1:
            raise ModelError("模型未返回恰好一个工具动作")
        function = calls[0]["function"]
        return self._parse_action(function["name"], function["arguments"])


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
            return action("finish", {"status": "needs_input", "message": "请补充关键信息", "questions": ["请问" + "、".join(LABELS[key] for key in missing) + "分别是什么？"]}, "输入字段不完整")
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
            self.base_script = mock_script(material, fact, request["target_duration_seconds"])
            script = copy.deepcopy(self.base_script)
            if self.scenario == "duration_revision":
                script["scenes"][0]["voiceover"] = "字幕" * 80
            return action("estimate_duration", {"script": script,
                                                "target_duration_seconds": request["target_duration_seconds"]}, "生成离线测试草稿后估时")
        if last["decision"]["action"] == "estimate_duration":
            script = copy.deepcopy(last["decision"]["arguments"]["script"])
            if result["status"] == "failed":
                if script["version"] >= 2:
                    return action("finish", {"status": "constraints_unsatisfied", "message": "压缩后仍无法满足时长", "questions": []}, "观察到第二版仍超限")
                version = script["version"] + 1
                script = copy.deepcopy(self.base_script)
                script["version"] = version
                return action("estimate_duration", {"script": script, "target_duration_seconds": request["target_duration_seconds"]}, "根据超时反馈压缩并重新估时")
            return action("check_rules", {"script": script}, "时长通过，检查事实和品牌规则")
        if result.get("facts") == "passed" and result.get("brand") == "passed":
            return action("finish", {"status": "completed", "message": "脚本已通过检查", "questions": []}, "当前版本检查均已通过")
        return action("finish", {"status": "constraints_unsatisfied", "message": "脚本规则检查未通过", "questions": []}, "仍有未解决规则问题")


def mock_script(material, fact, target):
    """Editable deterministic fixture, not a real-model output."""
    narratives = [
        ("创作者面对镜头，停下手中的拍摄准备，切到手写重点的纸卡。",
         "拍口播时，你最想让观众记住哪句话？先把它写下来，再看这一段画面。"),
        ("切到写着产品事实的文字卡，再回到创作者准备的内容提纲。",
         "这次介绍的产品事实很简单：" + fact["text"] + "。先围绕这一点，安排你的内容。"),
        ("回到口播画面，创作者指向自己的提纲，最后停在评论区提问的文字卡。",
         "回到你准备发布的抖音视频，把重点放在哪里，由你来决定。评论区聊聊你的想法。"),
    ]
    if target < 10:
        narratives = [("产品画面", fact["text"])]
    scenes = []
    for index, (visual, voiceover) in enumerate(narratives, 1):
        claims = []
        if fact["text"] in voiceover:
            claims = [{"text": fact["text"], "source_id": material["id"], "fact_id": fact["id"]}]
        scenes.append({"id": f"S{index:02}", "visual": visual, "voiceover": voiceover,
                       "subtitle": voiceover, "claims": claims})
    return {"version": 1, "title": "拍口播时，你想让观众记住哪句话？", "scenes": scenes}
