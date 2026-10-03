"""Middleware ASGI que registra cada petición HTTP en Argus."""

from __future__ import annotations

import secrets
from time import perf_counter

from starlette.routing import Match
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from src.agents.monitoring_agent.collector import UNMATCHED_ROUTE, MetricsCollector, agent_for_route

PROBE_HEADER = "x-argus-probe"
PROBE_TOKEN = secrets.token_hex(16)


def resolve_route(routes_app, scope: Scope) -> str:
    partial = None
    for route in getattr(routes_app, "routes", []):
        match, _ = route.matches(scope)
        if match == Match.FULL:
            return getattr(route, "path", UNMATCHED_ROUTE)
        if match == Match.PARTIAL and partial is None:
            partial = getattr(route, "path", None)
    return partial or UNMATCHED_ROUTE


class ArgusMiddleware:
    def __init__(self, app: ASGIApp, collector: MetricsCollector, routes_app) -> None:
        self.app = app
        self.collector = collector
        self.routes_app = routes_app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers") or [])
        if headers.get(PROBE_HEADER.encode()) == PROBE_TOKEN.encode():
            await self.app(scope, receive, send)
            return

        status = {"code": 500}

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
            await send(message)

        start = perf_counter()
        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            route = resolve_route(self.routes_app, scope)
            self.collector.record(
                agent_for_route(route), scope.get("method", "GET"), route, status["code"], (perf_counter() - start) * 1000
            )
