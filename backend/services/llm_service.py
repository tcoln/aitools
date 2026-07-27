# Author: glt
# Email: guolintan@qq.com
# Created: 2026-07-22

import json
import logging
from typing import AsyncGenerator
import httpx

from config import settings
from services.mcp_client import mcp_client_manager

logger = logging.getLogger(__name__)


# LLM服务：统一管理OpenAI、Ollama、ChatABC的对话、工具调用、模型查询
class LLMService:

    # 初始化LLM服务，创建模型提供商缓存字典和ChatABC会话缓存
    def __init__(self):
        self._model_providers: dict[str, str] = {}
        self._chatabc_sessions: dict[str, str] = {}

    # 判断当前模型是否为Ollama提供
    def _is_ollama(self, model: str | None = None) -> bool:
        if settings.LLM_PROVIDER == "ollama":
            return True
        if settings.LLM_PROVIDER == "openai":
            return False
        if model and model in self._model_providers:
            return self._model_providers[model] == "ollama"
        return False

    # 判断当前模型是否为ChatABC提供
    def _is_chatabc(self, model: str | None = None) -> bool:
        if settings.LLM_PROVIDER == "chatabc":
            return True
        if model and model in self._model_providers:
            return self._model_providers[model] == "chatabc"
        return False

    # 流式调用OpenAI兼容API
    async def _stream_openai(
        self, model: str, messages: list[dict], functions: list[dict] | None,
        tool_choice: str | None = None,
    ) -> AsyncGenerator[dict, None]:
        url = f"{settings.OPENAI_API_BASE}/chat/completions"
        body = {"model": model, "messages": messages, "stream": True}
        if functions:
            body["tools"] = functions
            if tool_choice:
                body["tool_choice"] = tool_choice

        headers = {
            "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=httpx.Timeout(connect=30.0, read=300.0, write=60.0, pool=30.0)) as client:
            async with client.stream("POST", url, json=body, headers=headers) as resp:
                if resp.status_code != 200:
                    error_body = ""
                    try:
                        error_body = await resp.aread()
                        error_body = error_body.decode("utf-8", errors="replace")[:500]
                    except Exception:
                        pass
                    raise Exception(f"OpenAI API error {resp.status_code}: {error_body}")
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break
                    try:
                        yield json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

    # 流式调用ChatABC Agent服务（自带会话管理和工具调用，只返回内容流）
    async def _stream_chatabc(
        self, messages: list[dict],
        conversation_id: str = "",
    ) -> AsyncGenerator[dict, None]:
        from services.chatabc_service import chatabc_service

        session_id = self._chatabc_sessions.get(conversation_id) if conversation_id else None

        if not session_id:
            result = await chatabc_service.init_session()
            session_id = result["session_id"]
            if conversation_id:
                self._chatabc_sessions[conversation_id] = session_id

        txt = ""
        for m in messages:
            if m["role"] == "user":
                txt = m["content"]
            elif m["role"] == "assistant" and m.get("content"):
                txt = f"[历史回复]: {m['content']}\n\n用户: {txt}"

        logger.info(f"ChatABC chat: session_id={session_id}, txt_len={len(txt)}")

        async for event in chatabc_service.chat(session_id, txt, stream=True):
            evt_type = event["event"]
            evt_data = event["data"]
            if evt_type == "chunk":
                content = evt_data.get("content", "")
                if content:
                    yield {"type": "content", "content": content}
            elif evt_type == "failed":
                raise Exception(f"ChatABC error: {json.dumps(evt_data, ensure_ascii=False)}")
            elif evt_type == "done":
                if evt_data.get("status") != "success":
                    raise Exception(f"ChatABC done with error: {json.dumps(evt_data, ensure_ascii=False)}")

    # 流式调用Ollama API
    async def _stream_ollama(
        self, model: str, messages: list[dict], functions: list[dict] | None,
        tool_choice: str | None = None,
    ) -> AsyncGenerator[dict, None]:
        url = f"{settings.OLLAMA_API_BASE}/api/chat"
        body = {"model": model, "messages": messages, "stream": True}
        if functions:
            body["tools"] = functions
            if tool_choice:
                body["tool_choice"] = tool_choice

        logger.info(f"Ollama request: model={model}, tools={len(functions or [])}")
        async with httpx.AsyncClient(timeout=httpx.Timeout(connect=30.0, read=600.0, write=60.0, pool=30.0)) as client:
            async with client.stream("POST", url, json=body) as resp:
                if resp.status_code != 200:
                    error_body = ""
                    try:
                        error_body = await resp.aread()
                        error_body = error_body.decode("utf-8", errors="replace")[:500]
                    except Exception:
                        pass
                    raise Exception(f"Ollama API error {resp.status_code}: {error_body}")
                async for line in resp.aiter_lines():
                    try:
                        data = json.loads(line)
                        if "error" in data:
                            raise Exception(f"Ollama error: {data['error']}")
                        yield data
                    except json.JSONDecodeError:
                        continue

    # 第一轮LLM对话：发送用户消息，LLM决定是否调用工具
    async def chat(
        self,
        message: str,
        history: list[dict],
        mcp_tools: list[dict],
        model: str | None = None,
        conversation_id: str = "",
    ) -> AsyncGenerator[dict, None]:
        model = model or settings.OPENAI_MODEL
        logger.info(f"LLM chat: model={model}, provider=ollama={self._is_ollama(model)}, chatabc={self._is_chatabc(model)}")

        if self._is_chatabc(model):
            messages = history + [{"role": "user", "content": message}]
            async for event in self._stream_chatabc(messages, conversation_id):
                yield event
            return

        functions = self._convert_mcp_tools_to_openai(mcp_tools) if mcp_tools else None
        messages = history + [{"role": "user", "content": message}]

        collected_content = ""
        collected_tool_calls = []

        if self._is_ollama(model):
            stream = self._stream_ollama(model, messages, functions, "auto")
        else:
            stream = self._stream_openai(model, messages, functions, "auto")

        async for data in stream:
            if "message" in data:
                msg = data["message"]
                if "content" in msg and msg["content"]:
                    collected_content += msg["content"]
                    yield {"type": "content", "content": msg["content"]}
                if "tool_calls" in msg:
                    for tc in msg["tool_calls"]:
                        func = tc.get("function", {})
                        args = func.get("arguments", {})
                        if isinstance(args, dict):
                            args_str = json.dumps(args, ensure_ascii=False)
                        elif isinstance(args, str):
                            args_str = args
                        else:
                            args_str = "{}"
                        collected_tool_calls.append({
                            "id": tc.get("id", ""),
                            "function": {
                                "name": func.get("name", ""),
                                "arguments": args_str,
                            }
                        })
            elif "choices" in data:
                delta = data.get("choices", [{}])[0].get("delta", {})
                if "content" in delta and delta["content"]:
                    collected_content += delta["content"]
                    yield {"type": "content", "content": delta["content"]}
                if "tool_calls" in delta:
                    for tc in delta["tool_calls"]:
                        idx = tc.get("index", 0)
                        while len(collected_tool_calls) <= idx:
                            collected_tool_calls.append({
                                "id": "",
                                "function": {"name": "", "arguments": ""}
                            })
                        if "id" in tc:
                            collected_tool_calls[idx]["id"] = tc["id"]
                        if "function" in tc:
                            if "name" in tc["function"] and tc["function"]["name"]:
                                collected_tool_calls[idx]["function"]["name"] = tc["function"]["name"]
                            if "arguments" in tc["function"]:
                                collected_tool_calls[idx]["function"]["arguments"] += tc["function"]["arguments"]

        if collected_tool_calls:
            yield {"type": "tool_calls", "tool_calls": collected_tool_calls}
        elif not collected_content:
            raise Exception("LLM 未返回任何内容，请检查模型是否正确或 API 是否可用")

    # 执行工具调用：遍历tool_calls，通过MCP客户端执行对应的工具
    async def execute_tool_calls(
        self,
        tool_calls: list[dict],
        mcp_services: list[dict],
        tool_to_service_map: dict,
    ) -> AsyncGenerator[dict, None]:
        results = []
        for tc in tool_calls:
            func_name = tc["function"]["name"]
            try:
                func_args = json.loads(tc["function"]["arguments"])
            except json.JSONDecodeError:
                func_args = {}

            service_name = tool_to_service_map.get(func_name)
            if not service_name:
                results.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": json.dumps({"error": f"Tool {func_name} not found"}),
                })
                continue

            service_config = next(
                (s for s in mcp_services if s["name"] == service_name), None
            )
            if not service_config:
                results.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": json.dumps({"error": f"Service {service_name} not found"}),
                })
                continue

            yield {"type": "tool_start", "tool_name": func_name, "arguments": func_args}

            result = await mcp_client_manager.call_tool(
                service_config, func_name, func_args
            )
            results.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": json.dumps(result, ensure_ascii=False),
            })
            yield {"type": "tool_result", "tool_name": func_name, "result": result}

        yield {"type": "tool_results_complete", "results": results}

    # 第二轮LLM对话：将工具执行结果送回LLM，生成最终文本回复
    async def chat_with_tool_results(
        self,
        messages: list[dict],
        mcp_tools: list[dict],
        model: str | None = None,
        conversation_id: str = "",
    ) -> AsyncGenerator[str, None]:
        model = model or settings.OPENAI_MODEL

        if self._is_chatabc(model):
            async for event in self._stream_chatabc(messages, conversation_id):
                if event["type"] == "content":
                    yield event["content"]
            return

        functions = self._convert_mcp_tools_to_openai(mcp_tools) if mcp_tools else None

        if self._is_ollama(model):
            for msg in messages:
                if msg.get("role") == "assistant" and "tool_calls" in msg:
                    for tc in msg["tool_calls"]:
                        args = tc["function"].get("arguments")
                        if isinstance(args, str):
                            try:
                                tc["function"]["arguments"] = json.loads(args)
                            except json.JSONDecodeError:
                                tc["function"]["arguments"] = {}
            stream = self._stream_ollama(model, messages, functions, "auto")
        else:
            stream = self._stream_openai(model, messages, functions, "auto")

        async for data in stream:
            if "message" in data:
                content = data["message"].get("content", "")
                if content:
                    yield content
            elif "choices" in data:
                delta = data.get("choices", [{}])[0].get("delta", {})
                if "content" in delta and delta["content"]:
                    yield delta["content"]

    # 从Ollama、OpenAI和ChatABC获取可用模型列表
    async def fetch_models(self) -> list[dict]:
        models = []
        self._model_providers = {}

        if settings.LLM_PROVIDER in ("chatabc", "all"):
            chatabc_model = settings.CHATABC_MODEL
            models.append({
                "id": chatabc_model,
                "provider": "abc",
                "name": f"ChatABC Agent",
            })
            self._model_providers[chatabc_model] = "chatabc"

        if settings.LLM_PROVIDER == "ollama" or settings.LLM_PROVIDER == "all":
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.get(f"{settings.OLLAMA_API_BASE}/api/tags")
                    if resp.status_code == 200:
                        data = resp.json()
                        for m in data.get("models", []):
                            mid = m["name"]
                            models.append({
                                "id": mid,
                                "provider": "ollama",
                                "name": mid,
                            })
                            self._model_providers[mid] = "ollama"
            except Exception:
                pass

        if settings.LLM_PROVIDER == "openai" or settings.LLM_PROVIDER == "all":
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.get(
                        f"{settings.OPENAI_API_BASE}/models",
                        headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        for m in data.get("data", []):
                            mid = m["id"]
                            models.append({
                                "id": mid,
                                "provider": "openai",
                                "name": mid,
                            })
                            self._model_providers[mid] = "openai"
            except Exception:
                pass

        if not models:
            fallback_model = settings.OPENAI_MODEL
            if settings.LLM_PROVIDER == "ollama" and not settings.OPENAI_MODEL:
                fallback_model = "qwen3:0.6b"
            models.append({
                "id": fallback_model,
                "provider": settings.LLM_PROVIDER,
                "name": fallback_model,
            })
            self._model_providers[fallback_model] = settings.LLM_PROVIDER
        return models

    # 将MCP工具定义转换为OpenAI function calling格式
    def _convert_mcp_tools_to_openai(self, mcp_tools: list[dict]) -> list[dict]:
        openai_tools = []
        for tool in mcp_tools:
            openai_tool = {
                "type": "function",
                "function": {
                    "name": tool.get("name", ""),
                    "description": tool.get("description", ""),
                    "parameters": tool.get("inputSchema", {"type": "object", "properties": {}}),
                }
            }
            openai_tools.append(openai_tool)
        return openai_tools


llm_service = LLMService()