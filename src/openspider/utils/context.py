# -*- coding: utf-8 -*-
"""Request-scoped context variables for OpenSpider.

Provides a ``ContextVar``-based ``request_id`` that is set by
``CorrelationIDMiddleware`` at the HTTP boundary and propagates
automatically through ``asyncio`` tasks spawned within the same context.

Usage::

    from openspider.utils.context import request_id_ctx

    # Read the current request ID (empty string if not set)
    rid = request_id_ctx.get()

    # Override for a specific async sub-task
    token = request_id_ctx.set("my-task-id")
    try:
        ...
    finally:
        request_id_ctx.reset(token)

The middleware also echoes the ``X-Request-Id`` header back in the
response so clients can correlate log lines to their requests.
"""
from __future__ import annotations

import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

#: Current request ID for the executing coroutine / task.
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")

_REQUEST_ID_HEADER = "X-Request-Id"


class CorrelationIDMiddleware(BaseHTTPMiddleware):
    """Starlette middleware that stamps every request with a correlation ID.

    - If the incoming request already carries an ``X-Request-Id`` header,
      that value is used verbatim (max 128 chars to prevent header injection).
    - Otherwise a new UUID4 is generated.

    The ID is stored in ``request_id_ctx`` for the duration of the request
    and returned as ``X-Request-Id`` in the response.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        incoming = (request.headers.get(_REQUEST_ID_HEADER) or "").strip()
        # Clamp length to prevent header injection / log poisoning
        rid = incoming[:128] if incoming else str(uuid.uuid4())

        token = request_id_ctx.set(rid)
        try:
            response: Response = await call_next(request)
        finally:
            request_id_ctx.reset(token)

        response.headers[_REQUEST_ID_HEADER] = rid
        return response
