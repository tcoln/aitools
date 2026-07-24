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
        "username": f"chatabc_integration_{int(time.time())}",
        "password": "Test1234!",
        "email": "test@example.com",
    })
    if resp.status_code == 200:
        return resp.json()["access_token"]
    resp = httpx.post(f"{BASE}/api/auth/login", json={
        "username": "chatabc_tester",
        "password": "Test1234!",
    })
    if resp.status_code == 200:
        return resp.json()["access_token"]
    raise Exception(f"Cannot get token: {resp.status_code}")


def test_models_list(headers):
    print("\n" + "=" * 60)
    print("测试 1: GET /api/chat/models — 确认 ChatABC 模型出现在列表中")
    print("=" * 60)
    resp = httpx.get(f"{BASE}/api/chat/models", headers=headers)
    print(f"  状态码: {resp.status_code}")
    models = resp.json()
    for m in models:
        print(f"  - {m['id']} (provider={m['provider']})")
    chatabc_models = [m for m in models if m["provider"] == "chatabc"]
    ok = len(chatabc_models) > 0
    print(f"  结果: {PASS if ok else FAIL}")
    chatabc_model_id = chatabc_models[0]["id"] if chatabc_models else None
    return chatabc_model_id


def test_chat_with_chatabc(headers, model_id):
    print("\n" + "=" * 60)
    print(f"测试 2: POST /api/chat/send — 使用 ChatABC 模型 ({model_id}) 发送消息")
    print("=" * 60)

    full_content = ""
    events = []

    with httpx.stream(
        "POST",
        f"{BASE}/api/chat/send",
        json={
            "message": "你好，请介绍一下你自己",
            "model": model_id,
        },
        headers=headers,
        timeout=60.0,
    ) as resp:
        print(f"  状态码: {resp.status_code}")
        for line in resp.iter_lines():
            if not line:
                continue
            if line.startswith("data: "):
                data_str = line[5:]
                try:
                    data = json.loads(data_str)
                except json.JSONDecodeError:
                    continue
                events.append(data)
                if data["type"] == "content":
                    full_content += data["content"]
                elif data["type"] == "done":
                    print(f"  conversation_id: {data.get('conversation_id', 'N/A')}")

    event_types = [e["type"] for e in events]
    print(f"  收到事件类型: {event_types}")
    print(f"  完整回复: {full_content}")

    ok = "content" in event_types and "done" in event_types and len(full_content) > 0
    print(f"  结果: {PASS if ok else FAIL}")
    return ok


def test_multi_turn(headers, model_id):
    print("\n" + "=" * 60)
    print(f"测试 3: 多轮对话 — 同一 conversation_id 发送两轮消息")
    print("=" * 60)

    # First turn
    full_content_1 = ""
    conv_id = None
    with httpx.stream(
        "POST",
        f"{BASE}/api/chat/send",
        json={"message": "你好，我叫小明", "model": model_id},
        headers=headers,
        timeout=60.0,
    ) as resp:
        for line in resp.iter_lines():
            if line.startswith("data: "):
                data = json.loads(line[5:])
                if data["type"] == "content":
                    full_content_1 += data["content"]
                elif data["type"] == "done":
                    conv_id = data.get("conversation_id")

    print(f"  第1轮回复: {full_content_1[:80]}...")
    print(f"  conversation_id: {conv_id}")

    # Second turn
    full_content_2 = ""
    with httpx.stream(
        "POST",
        f"{BASE}/api/chat/send",
        json={"message": "我叫什么名字？", "model": model_id, "conversation_id": conv_id},
        headers=headers,
        timeout=60.0,
    ) as resp:
        for line in resp.iter_lines():
            if line.startswith("data: "):
                data = json.loads(line[5:])
                if data["type"] == "content":
                    full_content_2 += data["content"]

    print(f"  第2轮回复: {full_content_2[:80]}...")

    ok = len(full_content_1) > 0 and len(full_content_2) > 0 and conv_id is not None
    print(f"  结果: {PASS if ok else FAIL}")
    return ok


def main():
    print("╔══════════════════════════════════════════════════════════╗")
    print("║       ChatABC 模型集成测试 (通过 /api/chat/send)         ║")
    print("╚══════════════════════════════════════════════════════════╝")

    token = get_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    print(f"\n获取认证令牌: {PASS}")

    model_id = test_models_list(headers)
    if not model_id:
        print("\nChatABC 模型不在列表中，无法继续测试")
        return

    results = [
        ("模型列表包含 ChatABC", True),
        ("ChatABC 单轮对话", test_chat_with_chatabc(headers, model_id)),
        ("ChatABC 多轮对话", test_multi_turn(headers, model_id)),
    ]

    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    for name, ok in results:
        print(f"  {PASS if ok else FAIL} {name}")

    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    if passed == total:
        print(f"\n  🎉 所有测试通过！ChatABC 已成功集成到模型选择中。")
    else:
        print(f"\n  ⚠️  通过 {passed}/{total}")


if __name__ == "__main__":
    main()