import json
import logging
from typing import AsyncGenerator
import httpx

from config import settings
from services.mcp_client import mcp_client_manager

logger = logging.getLogger(__name__)


class LLMService:

    def __init__(self):
        self._model_providers: dict[str, str] = {}

    def _is_ollama(self, model: str | None = None) -> bool:
        if settings.LLM_PROVIDER == "ollama":
            return True
        if settings.LLM_PROVIDER == "openai":
            return False
        if model and model in self._model_providers:
            return self._model_providers[model] == "ollama"
        return False

    async def _stream_openai(
        self, model: str, messages: list[dict], functions: list[dict] | None,
        tool_choice: str | None = None,
    ) -> AsyncGenerator[dict, None]:
        url = f"{settings.LLM_API_BASE}/chat/completions"
        body = {"model": model, "messages": messages, "stream": True}
        if functions:
            body["tools"] = functions
            if tool_choice:
                body["tool_choice"] = tool_choice

        headers = {
            "Authorization": f"Bearer {settings.LLM_API_KEY}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=120) as client:
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

    async def _stream_ollama(
        self, model: str, messages: list[dict], functions: list[dict] | None,
    ) -> AsyncGenerator[dict, None]:
        url = f"{settings.OLLAMA_API_BASE}/api/chat"
        body = {"model": model, "messages": messages, "stream": True}
        if functions:
            body["tools"] = functions

        logger.info(f"Ollama request: model={model}, tools={len(functions or [])}")
        async with httpx.AsyncClient(timeout=120) as client:
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

    async def chat(
        self,
        message: str,
        history: list[dict],
        mcp_tools: list[dict],
        model: str | None = None,
    ) -> AsyncGenerator[dict, None]:
        model = model or settings.LLM_MODEL
        logger.info(f"LLM chat: model={model}, provider=ollama={self._is_ollama(model)}")
        functions = self._convert_mcp_tools_to_openai(mcp_tools) if mcp_tools else None
        messages = history + [{"role": "user", "content": message}]

        collected_content = ""
        collected_tool_calls = []

        if self._is_ollama(model):
            stream = self._stream_ollama(model, messages, functions)
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

    async def chat_with_tool_results(
        self,
        messages: list[dict],
        mcp_tools: list[dict],
        model: str | None = None,
    ) -> AsyncGenerator[str, None]:
        model = model or settings.LLM_MODEL
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
            stream = self._stream_ollama(model, messages, functions)
        else:
            stream = self._stream_openai(model, messages, functions)

        async for data in stream:
            if "message" in data:
                content = data["message"].get("content", "")
                if content:
                    yield content
            elif "choices" in data:
                delta = data.get("choices", [{}])[0].get("delta", {})
                if "content" in delta and delta["content"]:
                    yield delta["content"]

    async def fetch_models(self) -> list[dict]:
        models = []
        self._model_providers = {}
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
                        f"{settings.LLM_API_BASE}/models",
                        headers={"Authorization": f"Bearer {settings.LLM_API_KEY}"},
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
            models.append({
                "id": settings.LLM_MODEL,
                "provider": settings.LLM_PROVIDER,
                "name": settings.LLM_MODEL,
            })
            self._model_providers[settings.LLM_MODEL] = settings.LLM_PROVIDER
        return models

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