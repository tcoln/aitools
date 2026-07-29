# Author: glt
# Email: guolintan@qq.com
# Created: 2026-07-23

import json
import time
import uuid
import logging
from typing import AsyncGenerator

import httpx

from config import settings

logger = logging.getLogger(__name__)


class ChatABCService:

    def _base_url(self) -> str:
        base = settings.CHATABC_API_BASE.rstrip("/")
        return f"{base}/chatabc"

    def _headers(self) -> dict:
        headers = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }
        if settings.CHATABC_API_KEY:
            headers["Authorization"] = f"Bearer {settings.CHATABC_API_KEY}"
        return headers

    def _common_body(self) -> dict:
        return {
            "appId": settings.CHATABC_APP_ID,
            "trCode": settings.CHATABC_TR_CODE,
            "trVersion": settings.CHATABC_TR_VERSION,
            "timestamp": int(time.time() * 1000),
            "requestId": str(uuid.uuid4()),
        }

    async def init_session(
        self, prompt_variables: list[dict] | None = None,
        tools: list[dict] | None = None,
    ) -> dict:
        url = f"{self._base_url()}/init_session"
        body = self._common_body()
        body["data"] = {}
        if prompt_variables:
            body["data"]["prompt_variables"] = prompt_variables
        if tools:
            body["data"]["tools"] = tools

        async with httpx.AsyncClient(timeout=30.0, verify=False) as client:
            resp = await client.post(url, json=body, headers=self._headers())
            if resp.status_code != 200:
                raise Exception(f"init_session failed: {resp.status_code} {resp.text[:500]}")
            result = resp.json()

            if "data" in result:
                return result["data"]

            raise Exception(
                f"init_session 返回格式异常: {json.dumps(result, ensure_ascii=False)[:500]}"
            )

    async def upload_file(
        self, session_id: str, filename: str, file_content: bytes,
        content_type: str = "application/octet-stream",
    ) -> dict:
        url = f"{self._base_url()}/upload_file"
        headers = {}
        if settings.CHATABC_API_KEY:
            headers["Authorization"] = f"Bearer {settings.CHATABC_API_KEY}"
        files = {
            "file": (filename, file_content, content_type),
        }
        data = {"session_id": session_id}

        async with httpx.AsyncClient(timeout=60.0, verify=False) as client:
            resp = await client.post(url, data=data, files=files, headers=headers)
            if resp.status_code != 200:
                raise Exception(f"upload_file failed: {resp.status_code} {resp.text[:500]}")
            result = resp.json()

            if "data" in result:
                return result["data"]

            raise Exception(
                f"upload_file 返回格式异常: {json.dumps(result, ensure_ascii=False)[:500]}"
            )

    async def chat(
        self,
        session_id: str,
        txt: str,
        files: list[dict] | None = None,
        stream: bool = True,
        tools: list[dict] | None = None,
    ) -> AsyncGenerator[dict, None]:
        url = f"{self._base_url()}/chat"
        body = self._common_body()
        body["data"] = {
            "session_id": session_id,
            "txt": txt,
            "files": files or [],
            "stream": stream,
        }
        if tools:
            body["data"]["tools"] = tools

        headers = self._headers()

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(connect=30.0, read=300.0, write=60.0, pool=30.0),
            verify=False,
        ) as client:
            async with client.stream("POST", url, json=body, headers=headers) as resp:
                if resp.status_code != 200:
                    error_body = ""
                    try:
                        error_body = await resp.aread()
                        error_body = error_body.decode("utf-8", errors="replace")[:500]
                    except Exception:
                        pass
                    raise Exception(f"chat failed: {resp.status_code} {error_body}")

                current_event = None
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    if line.startswith("event:"):
                        current_event = line[6:].strip()
                        continue
                    if line.startswith("data:") and current_event:
                        data_str = line[5:].strip()
                        try:
                            data = json.loads(data_str)
                        except json.JSONDecodeError:
                            data = {"raw": data_str}
                        yield {"event": current_event, "data": data}
                        if current_event == "done":
                            return
                        current_event = None

    async def download_file(
        self, session_id: str, filename: str,
    ) -> bytes:
        url = f"{self._base_url()}/download_file"
        headers = {}
        if settings.CHATABC_API_KEY:
            headers["Authorization"] = f"Bearer {settings.CHATABC_API_KEY}"
        params = {"session_id": session_id, "filename": filename}

        async with httpx.AsyncClient(timeout=60.0, verify=False) as client:
            resp = await client.get(url, params=params, headers=headers)
            if resp.status_code != 200:
                raise Exception(f"download_file failed: {resp.status_code} {resp.text[:500]}")
            return resp.content

    async def fetch_history(
        self,
        session_id: str,
        jsonpath: str | None = None,
    ) -> dict:
        url = f"{self._base_url()}/fetch_history"
        body = self._common_body()
        body["data"] = {"session_id": session_id}
        if jsonpath:
            body["data"]["jsonpath"] = jsonpath

        headers = {
            "Content-Type": "application/json",
        }
        if settings.CHATABC_API_KEY:
            headers["Authorization"] = f"Bearer {settings.CHATABC_API_KEY}"

        async with httpx.AsyncClient(timeout=30.0, verify=False) as client:
            resp = await client.post(url, json=body, headers=headers)
            if resp.status_code != 200:
                raise Exception(f"fetch_history failed: {resp.status_code} {resp.text[:500]}")
            return resp.json()


chatabc_service = ChatABCService()