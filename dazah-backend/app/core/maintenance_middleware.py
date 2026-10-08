"""Track admitted requests through ASGI completion, including dependency cleanup."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from collections.abc import Awaitable
from typing import cast

from redis.exceptions import RedisError
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.maintenance import MaintenanceActiveError, business_activity
from app.core.redis import redis_client

OPERATION_ID = re.compile(
    r"^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$"
)
WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
CLAIM = """
if redis.call('HEXISTS', KEYS[1], ARGV[1]) == 1 then return 0 end
redis.call('HSET', KEYS[1], ARGV[1], ARGV[2])
redis.call('PERSIST', KEYS[1])
return 1
"""
READ_START = """
redis.call('HSET', KEYS[1], ARGV[1], ARGV[2])
redis.call('PERSIST', KEYS[1])
return 1
"""
COMPLETE = """
redis.call('HSET', KEYS[1], ARGV[1], ARGV[2])
local writes = false
for _, value in ipairs(redis.call('HVALS', KEYS[1])) do
  local record = cjson.decode(value)
  if record.method ~= 'GET' and record.method ~= 'HEAD'
      and record.method ~= 'OPTIONS' then
    writes = true
  end
  if record.state == 'unknown' then
    redis.call('PERSIST', KEYS[1])
    return 0
  end
end
redis.call('EXPIRE', KEYS[1], writes and ARGV[3] or ARGV[4])
return 1
"""


def receipt_key(owner: str, operation_id: str) -> str:
    return f"dazah:operation:{owner}:{operation_id}"


class MaintenanceMiddleware:
    def __init__(self, app: ASGIApp, journal: bool = True) -> None:
        self.app = app
        self.journal = journal

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")
        if scope["type"] != "http" or not path.startswith(("/api/v1/", "/mcp")):
            await self.app(scope, receive, send)
            return
        request = Request(scope, receive)
        operation_id = request.headers.get("X-Dazah-Operation-ID")
        owner = str(scope.get("state", {}).get("audit_user_id") or "")
        write = request.method in WRITE_METHODS
        key: str | None = None
        field = ""
        receipt: dict[str, str | int | float] = {}
        downstream_receive: Receive = receive
        # Reads called through Server Actions also use POST in the browser.
        read = request.method in {"GET", "HEAD", "OPTIONS"}
        if self.journal and (write or read) and operation_id and owner:
            if not OPERATION_ID.fullmatch(operation_id):
                await JSONResponse({"message": "操作编号无效"}, status_code=422)(
                    scope, receive, send
                )
                return
            # No inputs, tokens or response bodies are retained. JSON requests
            # include a digest; other bodies are never buffered by this layer.
            body_hash = "unbuffered"
            if "application/json" in request.headers.get("content-type", ""):
                try:
                    size = int(request.headers.get("content-length", "0"))
                except ValueError:
                    size = 0
                if 0 < size <= 2 * 1024 * 1024:
                    body = await request.body()
                    body_hash = hashlib.sha256(body).hexdigest()
                    delivered = False

                    async def replay_receive() -> Message:
                        nonlocal delivered
                        if not delivered:
                            delivered = True
                            return {
                                "type": "http.request",
                                "body": body,
                                "more_body": False,
                            }
                        return await receive()

                    downstream_receive = replay_receive
                else:
                    downstream_receive = receive
            else:
                downstream_receive = receive
            # One Server Action may contain multiple distinct backend writes.
            # Each gets its own receipt within the same user-operation group.
            field = hashlib.sha256(
                (
                    f"{request.method}:{path}:"
                    f"{scope.get('query_string', b'').hex()}:{body_hash}"
                ).encode()
            ).hexdigest()
            key = receipt_key(owner, operation_id)
            receipt = {
                "method": request.method,
                "path": path,
                "state": "unknown",
                "updated_at": time.time(),
            }
        else:
            downstream_receive = receive

        status = 0

        async def observe_send(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            async with business_activity("request"):
                if key:
                    async with asyncio.timeout(3):
                        claimed = await cast(
                            Awaitable[int],
                            redis_client.eval(
                                CLAIM if write else READ_START,
                                1,
                                key,
                                field,
                                json.dumps(receipt),
                            ),
                        )
                    if not claimed:
                        await JSONResponse(
                            {
                                "message": "本次操作已受理，请先查询操作结果，"
                                "勿重复提交",
                                "operation_id": operation_id,
                            },
                            status_code=409,
                        )(scope, receive, send)
                        return
                await self.app(scope, downstream_receive, observe_send)
                if key:
                    receipt.update(
                        state="completed"
                        if 200 <= status < 300
                        else "rejected"
                        if 400 <= status < 500
                        else "unknown",
                        http_status=status,
                        updated_at=time.time(),
                    )
                    async with asyncio.timeout(3):
                        # Atomically retain pending siblings when another write
                        # joins this Server Action while completion is recorded.
                        await cast(
                            Awaitable[int],
                            redis_client.eval(
                                COMPLETE,
                                1,
                                key,
                                field,
                                json.dumps(receipt),
                                7 * 24 * 3600,
                                300,
                            ),
                        )
        except MaintenanceActiveError:
            await JSONResponse(
                {"message": "系统维护中，尚未受理本次操作"},
                status_code=503,
                headers={"X-Dazah-Maintenance": "1", "Retry-After": "15"},
            )(scope, receive, send)
        except (RedisError, TimeoutError):
            if status:
                raise
            await JSONResponse(
                {"message": "操作保护服务暂不可用，本次操作未受理"}, status_code=503
            )(scope, receive, send)
