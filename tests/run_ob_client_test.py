"""麦麦守门人 OneBotClient 集成自测。

在本机随机端口起一个模拟 OneBot v11 对端（aiohttp WS server），真实验证：
- 正向 WS 连接（token 双通道鉴权）
- 事件推送（无 echo 载荷 → on_event 回调）
- action 的 echo 匹配响应
- get_version_info 对端类型探测（napcat / snowluma）
- 断线自动重连
- stop() 干净退出
"""

from __future__ import annotations

import asyncio
import json
import sys
import traceback
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from aiohttp import WSMsgType, web

from Mai_gatekeeper.ob_client import OneBotClient, OneBotConnectionConfig

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(condition), detail))
    print(f"[{'PASS' if condition else 'FAIL'}] {name}" + (f" —— {detail}" if detail and not condition else ""))


class FakeOneBotServer:
    """模拟 OneBot v11 对端：校验鉴权，响应 action，可主动推事件。"""

    def __init__(self) -> None:
        self.app = web.Application()
        self.app.router.add_get("/", self.ws_handler)
        self.runner: web.AppRunner | None = None
        self.connections: list[Any] = []
        self.received: list[dict[str, Any]] = []
        self.app_name = "NapCat"
        self.fail_actions: set[str] = set()

    async def start(self) -> int:
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "127.0.0.1", 0)
        await site.start()
        return int(self.runner.addresses[0][1])

    async def stop(self) -> None:
        if self.runner is not None:
            await self.runner.cleanup()

    async def ws_handler(self, request: Any) -> web.WebSocketResponse:
        token = request.query.get("access_token") or ""
        auth = request.headers.get("Authorization", "")
        if token != "it-token" and auth != "Bearer it-token":
            raise web.HTTPUnauthorized()
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self.connections.append(ws)
        async for msg in ws:
            if msg.type != WSMsgType.TEXT:
                continue
            payload = json.loads(msg.data)
            self.received.append(payload)
            if "echo" not in payload:
                continue
            action = payload.get("action")
            if action in self.fail_actions:
                response = {"status": "failed", "retcode": 1200, "word": "FLAG已失效", "echo": payload["echo"]}
            elif action == "get_version_info":
                response = {
                    "status": "ok",
                    "retcode": 0,
                    "data": {"app_name": self.app_name, "app_version": "4.2.1"},
                    "echo": payload["echo"],
                }
            elif action == "get_stranger_info":
                response = {
                    "status": "ok",
                    "retcode": 0,
                    "data": {"user_id": payload["params"].get("user_id"), "nickname": "模拟昵称"},
                    "echo": payload["echo"],
                }
            else:
                response = {"status": "ok", "retcode": 0, "data": {}, "echo": payload["echo"]}
            await ws.send_str(json.dumps(response, ensure_ascii=False))
        return ws

    async def push_event(self, payload: dict[str, Any]) -> None:
        for ws in list(self.connections):
            if not ws.closed:
                await ws.send_str(json.dumps(payload, ensure_ascii=False))


async def wait_for(predicate: Any, timeout: float = 5.0) -> bool:
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.05)
    return predicate()


async def main() -> int:
    events: list[dict[str, Any]] = []
    server = FakeOneBotServer()
    port = await server.start()

    config = OneBotConnectionConfig(
        server="127.0.0.1",
        port=port,
        token="it-token",
        heartbeat_interval=0,
        reconnect_delay_sec=0.2,
        action_timeout_sec=5.0,
    )
    client = OneBotClient(on_event=lambda payload: events.append(payload) or asyncio.sleep(0))
    client.configure(config)
    await client.start()

    try:
        # 连接 + 探测
        check("连接成功", await wait_for(lambda: client.connected))
        check(
            "探测到对端类型 napcat",
            await wait_for(lambda: client.peer_info.client_type == "napcat" and client.peer_info.app_version == "4.2.1"),
        )

        # action echo 匹配
        response = await client.call_action("get_stranger_info", {"user_id": 12345})
        check(
            "action echo 响应正确",
            response.get("status") == "ok" and response["data"]["nickname"] == "模拟昵称",
            str(response),
        )
        check(
            "请求按标准格式发送",
            any(r["action"] == "get_stranger_info" and r["params"] == {"user_id": 12345} and r.get("echo") for r in server.received),
        )

        # 事件推送
        await server.push_event(
            {"post_type": "request", "request_type": "friend", "flag": "F1", "user_id": 777, "comment": "hi"}
        )
        check("事件回调收到好友申请", await wait_for(lambda: any(e.get("flag") == "F1" for e in events)))

        # snowluma 探测分支（换对端标识后断线重连，触发重新探测）
        server.app_name = "SnowLuma"
        for ws in list(server.connections):
            await ws.close()
        server.connections.clear()
        check(
            "重连后探测到 snowluma",
            await wait_for(lambda: client.peer_info.client_type == "snowluma"),
        )

        # 失败 action
        server.fail_actions = {"set_friend_add_request"}
        response = await client.call_action("set_friend_add_request", {"flag": "X", "approve": True})
        check("失败 action 透传 retcode", response.get("retcode") == 1200)

        # 断线重连
        for ws in list(server.connections):
            await ws.close()
        server.connections.clear()
        check("断连后进入未连接态", await wait_for(lambda: not client.connected))
        check("自动重连成功", await wait_for(lambda: client.connected, timeout=5.0))
        response = await client.call_action("get_version_info", {})
        check("重连后 action 可用", response.get("status") == "ok")

        # 鉴权失败场景（换 token 重连被拒）
        server.fail_actions.clear()
    except Exception:
        check("集成测试（未抛异常）", False, traceback.format_exc(limit=3))

    await client.stop()
    await server.stop()
    check("stop 后不再连接", not client.connected)

    # 错误 token → 一直重试不崩
    bad = OneBotClient(on_event=lambda p: asyncio.sleep(0))
    bad.configure(
        OneBotConnectionConfig(
            server="127.0.0.1", port=port, token="wrong", reconnect_delay_sec=0.1, action_timeout_sec=2.0
        )
    )
    server2 = FakeOneBotServer()
    port2 = await server2.start()
    bad._config = OneBotConnectionConfig(
        server="127.0.0.1", port=port2, token="wrong", reconnect_delay_sec=0.1, action_timeout_sec=2.0
    )
    await bad.start()
    await asyncio.sleep(0.6)
    check("错误 token 持续重试不崩溃", not bad.connected and bad._connection_task is not None and not bad._connection_task.done())
    await bad.stop()
    await server2.stop()

    passed = sum(1 for _, ok, _ in RESULTS if ok)
    print(f"\n===== OneBotClient 集成：{passed}/{len(RESULTS)} 通过 =====")
    for name, ok, detail in RESULTS:
        if not ok:
            print(f"FAIL: {name}\n{detail}")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
