#!/usr/bin/env python3
# Author: glt
# Email: guolintan@qq.com
# Created: 2026-07-23

import json
import time
import httpx

BASE = "http://localhost:8000"
PASS = "✅"
FAIL = "❌"


def get_token():
    resp = httpx.post(f"{BASE}/api/auth/register", json={
        "username": f"test_chatabc_{int(time.time())}",
        "password": "Test1234!",
        "email": "test@example.com",
    })
    if resp.status_code == 200:
        return resp.json()["access_token"]
    resp = httpx.post(f"{BASE}/api/auth/login", json={
        "username": f"test_chatabc_{int(time.time())}",
        "password": "Test1234!",
    })
    if resp.status_code != 200:
        resp = httpx.post(f"{BASE}/api/auth/register", json={
            "username": "chatabc_tester",
            "password": "Test1234!",
            "email": "tester@example.com",
        })
        if resp.status_code == 200:
            return resp.json()["access_token"]
        raise Exception(f"Cannot get token: {resp.status_code} {resp.text}")
    return resp.json()["access_token"]


def test_init_session(headers):
    print("\n" + "=" * 60)
    print("测试 1: POST /api/chatabc/init_session")
    print("=" * 60)
    resp = httpx.post(
        f"{BASE}/api/chatabc/init_session",
        json={"prompt_variables": [{"name": "var1", "value": "hello"}]},
        headers=headers,
    )
    print(f"  状态码: {resp.status_code}")
    print(f"  响应: {resp.json()}")
    ok = resp.status_code == 200 and "session_id" in resp.json()
    session_id = resp.json().get("session_id", "")
    print(f"  结果: {PASS if ok else FAIL}")
    return session_id


def test_upload_file(headers, session_id):
    print("\n" + "=" * 60)
    print("测试 2: POST /api/chatabc/upload_file")
    print("=" * 60)
    file_content = b"Hello, this is a test file content for ChatABC."
    resp = httpx.post(
        f"{BASE}/api/chatabc/upload_file",
        params={"session_id": session_id},
        files={"file": ("test_doc.txt", file_content, "text/plain")},
        headers={k: v for k, v in headers.items() if k != "Content-Type"},
    )
    print(f"  状态码: {resp.status_code}")
    print(f"  响应: {resp.json()}")
    ok = resp.status_code == 200
    print(f"  结果: {PASS if ok else FAIL}")
    return ok


def test_chat(headers, session_id):
    print("\n" + "=" * 60)
    print("测试 3: POST /api/chatabc/chat (SSE 流式)")
    print("=" * 60)
    events_collected = []
    full_content = ""
    with httpx.stream(
        "POST",
        f"{BASE}/api/chatabc/chat",
        json={
            "session_id": session_id,
            "txt": "你好，请介绍一下你自己",
            "files": [],
            "stream": True,
        },
        headers=headers,
        timeout=30.0,
    ) as resp:
        print(f"  状态码: {resp.status_code}")
        current_event = None
        for line in resp.iter_lines():
            if not line:
                continue
            if line.startswith("event:"):
                current_event = line[6:].strip()
            elif line.startswith("data:") and current_event:
                data_str = line[5:].strip()
                try:
                    data = json.loads(data_str)
                except json.JSONDecodeError:
                    data = {"raw": data_str}
                events_collected.append({"event": current_event, "data": data})
                if current_event == "chunk":
                    full_content += data.get("content", "")
                if current_event == "done":
                    break
                current_event = None

    event_types = [e["event"] for e in events_collected]
    print(f"  收到事件: {event_types}")
    print(f"  完整内容: {full_content}")
    ok = "chat_started" in event_types and "chunk" in event_types and "message" in event_types and "done" in event_types
    print(f"  结果: {PASS if ok else FAIL}")
    return ok


def test_download_file(headers, session_id):
    print("\n" + "=" * 60)
    print("测试 4: GET /api/chatabc/download_file")
    print("=" * 60)
    resp = httpx.get(
        f"{BASE}/api/chatabc/download_file",
        params={"session_id": session_id, "filename": "test_doc.txt"},
        headers=headers,
    )
    print(f"  状态码: {resp.status_code}")
    print(f"  Content-Type: {resp.headers.get('content-type', 'N/A')}")
    print(f"  内容长度: {len(resp.content)} bytes")
    if resp.status_code == 200 and "application/octet-stream" in resp.headers.get("content-type", ""):
        print(f"  内容预览: {resp.content[:60]}")
    ok = resp.status_code == 200 and len(resp.content) > 0
    print(f"  结果: {PASS if ok else FAIL}")
    return ok


def test_fetch_history(headers, session_id):
    print("\n" + "=" * 60)
    print("测试 5: POST /api/chatabc/fetch_history")
    print("=" * 60)
    resp = httpx.post(
        f"{BASE}/api/chatabc/fetch_history",
        json={"session_id": session_id},
        headers=headers,
    )
    print(f"  状态码: {resp.status_code}")
    result = resp.json()
    print(f"  响应: {json.dumps(result, ensure_ascii=False, indent=2)[:500]}")
    ok = resp.status_code == 200
    print(f"  结果: {PASS if ok else FAIL}")
    return ok


def main():
    print("╔══════════════════════════════════════════════════════════╗")
    print("║          ChatABC 接口集成测试                            ║")
    print("╚══════════════════════════════════════════════════════════╝")

    token = get_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    print(f"\n获取认证令牌: {PASS}")

    session_id = test_init_session(headers)
    if not session_id:
        print("\ninit_session 失败，无法继续后续测试")
        return

    results = []
    results.append(("init_session", True))
    results.append(("upload_file", test_upload_file(headers, session_id)))
    results.append(("chat", test_chat(headers, session_id)))
    results.append(("download_file", test_download_file(headers, session_id)))
    results.append(("fetch_history", test_fetch_history(headers, session_id)))

    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    for name, ok in results:
        print(f"  {PASS if ok else FAIL} {name}")

    total = len(results)
    passed = sum(1 for _, ok in results if ok)
    print(f"\n  通过: {passed}/{total}")
    if passed == total:
        print(f"\n  🎉 所有接口测试通过！")
    else:
        print(f"\n  ⚠️  有 {total - passed} 个接口测试失败")


if __name__ == "__main__":
    main()