# Author: glt
# Email: guolintan@qq.com
# Created: 2026-07-22

import json
import os
import asyncio
from typing import Any
import httpx

from config import settings


# MCP客户端管理器：管理stdio、SSE和Streamable HTTP三种传输协议的MCP工具调用
class MCPClientManager:

    def __init__(self):
        self._processes: dict[str, asyncio.subprocess.Process] = {}
        self._http_clients: dict[str, httpx.AsyncClient] = {}

    async def get_tools(self, service_config: dict) -> list[dict]:
        transport = service_config.get("transport_type", "stdio")
        if transport == "stdio":
            return await self._get_stdio_tools(service_config)
        elif transport == "sse":
            return await self._get_sse_tools(service_config)
        elif transport == "streamable-http":
            return await self._get_http_tools(service_config)
        else:
            return []

    async def call_tool(self, service_config: dict, tool_name: str, arguments: dict) -> Any:
        transport = service_config.get("transport_type", "stdio")
        if transport == "stdio":
            return await self._call_stdio_tool(service_config, tool_name, arguments)
        elif transport == "sse":
            return await self._call_sse_tool(service_config, tool_name, arguments)
        elif transport == "streamable-http":
            return await self._call_http_tool(service_config, tool_name, arguments)
        else:
            raise ValueError(f"Unsupported transport type: {transport}")

    # 通过stdio协议获取MCP工具列表
    async def _get_stdio_tools(self, config: dict) -> list[dict]:
        try:
            cmd = [config["command"]]
            if config.get("args"):
                cmd.extend(json.loads(config["args"]))
            env = os.environ.copy()
            if config.get("env_vars"):
                env.update(json.loads(config["env_vars"]))

            request = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/list",
                "params": {}
            }
            request_str = json.dumps(request) + "\n"

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(request_str.encode()), timeout=30
                )
                lines = stdout.decode().strip().split("\n")
                for line in lines:
                    if line.strip():
                        try:
                            response = json.loads(line)
                            if "result" in response and "tools" in response["result"]:
                                return response["result"]["tools"]
                        except json.JSONDecodeError:
                            continue
                return []
            finally:
                if proc.returncode is None:
                    proc.kill()
                    await proc.wait()
        except Exception as e:
            print(f"Error getting stdio tools: {e}")
            return []

    # 通过stdio协议调用MCP工具
    async def _call_stdio_tool(self, config: dict, tool_name: str, arguments: dict) -> Any:
        try:
            cmd = [config["command"]]
            if config.get("args"):
                cmd.extend(json.loads(config["args"]))
            env = os.environ.copy()
            if config.get("env_vars"):
                env.update(json.loads(config["env_vars"]))

            request = {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": arguments,
                }
            }
            request_str = json.dumps(request) + "\n"

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(request_str.encode()), timeout=60
                )
                lines = stdout.decode().strip().split("\n")
                for line in lines:
                    if line.strip():
                        try:
                            response = json.loads(line)
                            if "result" in response:
                                return response["result"]
                            if "error" in response:
                                return {"error": response["error"]}
                        except json.JSONDecodeError:
                            continue
                return {"error": "No valid response from MCP server"}
            finally:
                if proc.returncode is None:
                    proc.kill()
                    await proc.wait()
        except Exception as e:
            return {"error": str(e)}

    # ==================== SSE 传输协议（使用 fastmcp.Client） ====================

    async def _get_sse_tools(self, config: dict) -> list[dict]:
        try:
            url = config.get("url", "")
            if not url:
                return []
            from fastmcp import Client
            async with Client(url) as client:
                tools = await client.list_tools()
                return [
                    {
                        "name": t.name,
                        "description": t.description or "",
                        "inputSchema": t.inputSchema if hasattr(t, "inputSchema") else {},
                    }
                    for t in tools
                ]
        except Exception as e:
            print(f"Error getting SSE tools: {e}")
            return []

    async def _call_sse_tool(self, config: dict, tool_name: str, arguments: dict) -> Any:
        try:
            url = config.get("url", "")
            if not url:
                return {"error": "No URL configured"}
            from fastmcp import Client
            async with Client(url) as client:
                result = await client.call_tool(tool_name, arguments)
                if result.content:
                    return result.content[0].text
                return {"error": "No content in response"}
        except Exception as e:
            return {"error": str(e)}

    # ==================== Streamable HTTP 传输协议 ====================

    # 通过Streamable HTTP协议获取MCP工具列表
    async def _get_http_tools(self, config: dict) -> list[dict]:
        try:
            url = config.get("url", "")
            if not url:
                return []
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            }
            if config.get("headers"):
                headers.update(json.loads(config["headers"]))

            async with httpx.AsyncClient(timeout=30) as client:
                session_id = await self._init_http_session(client, url, headers)
                if session_id:
                    headers["Mcp-Session-Id"] = session_id

                resp = await client.post(
                    url,
                    json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
                    headers=headers,
                )
                if resp.status_code != 200:
                    print(f"MCP HTTP error: {resp.status_code} {resp.text[:200]}")
                    return []
                data = self._parse_sse_json(resp.text)
                if not data:
                    return []
                if "result" in data and "tools" in data["result"]:
                    return data["result"]["tools"]
                if "error" in data:
                    print(f"MCP JSON-RPC error: {data['error']}")
                return []
        except Exception as e:
            print(f"Error getting HTTP tools: {e}")
            return []

    # 通过Streamable HTTP协议调用MCP工具
    async def _call_http_tool(self, config: dict, tool_name: str, arguments: dict) -> Any:
        try:
            url = config.get("url", "")
            if not url:
                return {"error": "No URL configured"}
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            }
            if config.get("headers"):
                headers.update(json.loads(config["headers"]))

            async with httpx.AsyncClient(timeout=60) as client:
                session_id = await self._init_http_session(client, url, headers)
                if session_id:
                    headers["Mcp-Session-Id"] = session_id

                resp = await client.post(
                    url,
                    json={
                        "jsonrpc": "2.0",
                        "id": 2,
                        "method": "tools/call",
                        "params": {"name": tool_name, "arguments": arguments},
                    },
                    headers=headers,
                )
                data = self._parse_sse_json(resp.text)
                if not data:
                    return {"error": "No valid response from MCP server"}
                if "result" in data:
                    return data["result"]
                if "error" in data:
                    return {"error": data["error"]}
                return {"error": "No valid response from MCP server"}
        except Exception as e:
            return {"error": str(e)}

    # 解析SSE格式的JSON响应
    def _parse_sse_json(self, text: str) -> dict | None:
        for line in text.strip().split("\n"):
            if line.startswith("data: "):
                try:
                    return json.loads(line[6:])
                except json.JSONDecodeError:
                    continue
        return None

    # 初始化Streamable HTTP会话，返回Session ID
    async def _init_http_session(self, client: httpx.AsyncClient, url: str, headers: dict) -> str | None:
        try:
            resp = await client.post(
                url,
                json={
                    "jsonrpc": "2.0",
                    "id": 0,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "ai-tools", "version": "1.0.0"},
                    },
                },
                headers=headers,
            )
            session_id = resp.headers.get("Mcp-Session-Id")
            if session_id:
                return session_id
            return None
        except Exception as e:
            print(f"Error initializing MCP session: {e}")
            return None


mcp_client_manager = MCPClientManager()