import json
import os
import subprocess
import asyncio
from typing import Any
import httpx

from config import settings


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
        else:
            return []

    async def call_tool(self, service_config: dict, tool_name: str, arguments: dict) -> Any:
        transport = service_config.get("transport_type", "stdio")
        if transport == "stdio":
            return await self._call_stdio_tool(service_config, tool_name, arguments)
        elif transport == "sse":
            return await self._call_sse_tool(service_config, tool_name, arguments)
        else:
            raise ValueError(f"Unsupported transport type: {transport}")

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

    async def _get_sse_tools(self, config: dict) -> list[dict]:
        try:
            url = config.get("url", "")
            if not url:
                return []
            async with httpx.AsyncClient(timeout=30) as client:
                headers = {}
                if config.get("headers"):
                    headers = json.loads(config["headers"])
                resp = await client.post(
                    f"{url}/tools/list",
                    json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
                    headers=headers,
                )
                data = resp.json()
                if "result" in data and "tools" in data["result"]:
                    return data["result"]["tools"]
                return []
        except Exception as e:
            print(f"Error getting SSE tools: {e}")
            return []

    async def _call_sse_tool(self, config: dict, tool_name: str, arguments: dict) -> Any:
        try:
            url = config.get("url", "")
            if not url:
                return {"error": "No URL configured"}
            async with httpx.AsyncClient(timeout=60) as client:
                headers = {}
                if config.get("headers"):
                    headers = json.loads(config["headers"])
                resp = await client.post(
                    f"{url}/tools/call",
                    json={
                        "jsonrpc": "2.0",
                        "id": 2,
                        "method": "tools/call",
                        "params": {"name": tool_name, "arguments": arguments},
                    },
                    headers=headers,
                )
                return resp.json()
        except Exception as e:
            return {"error": str(e)}


mcp_client_manager = MCPClientManager()