"""A tiny raw-socket HTTP server that impersonates a Squid.

The API tests used to mock aiohttp. That hid a real defect: Squid firmware
answers a bad password with a malformed 401 (it declares Content-Length: 0 and
then writes a stray "0" body), which strict HTTP parsers reject outright. A
mock can only produce well-formed responses, so it could never reproduce that.

This server writes raw bytes straight onto the socket, so a test can reproduce
exactly what the hardware sends, byte for byte. It also keeps the suite free of
aioresponses, which does not work with the aiohttp that recent Home Assistant
releases ship.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RecordedRequest:
    """One request the fake device received."""

    method: str
    path: str
    headers: dict[str, str]
    body: bytes


def json_response(payload: Any, status: int = 200) -> bytes:
    """A well-formed JSON response."""
    body = json.dumps(payload).encode()
    head = (
        f"HTTP/1.1 {status} OK\r\n"
        f"Content-Type: application/json\r\n"
        f"Content-Length: {len(body)}\r\n"
        "Connection: close\r\n\r\n"
    ).encode()
    return head + body


def status_response(status: int, reason: str = "Error") -> bytes:
    """A well-formed empty response with the given status."""
    return (
        f"HTTP/1.1 {status} {reason}\r\n"
        "Content-Length: 0\r\n"
        "Connection: close\r\n\r\n"
    ).encode()


def raw_body_response(body: str, content_type: str = "text/html") -> bytes:
    """A well-formed 200 whose body is whatever you pass, valid JSON or not."""
    encoded = body.encode()
    head = (
        "HTTP/1.1 200 OK\r\n"
        f"Content-Type: {content_type}\r\n"
        f"Content-Length: {len(encoded)}\r\n"
        "Connection: close\r\n\r\n"
    ).encode()
    return head + encoded


# Captured verbatim from an SX-DC-8-12-120 on firmware 1.01.26815 by sending a
# request with a deliberately wrong password. Note the "0" after the blank line
# despite Content-Length: 0 -- that trailing byte is the firmware defect.
MALFORMED_401 = (
    b"HTTP/1.0 401 Access Error\r\n"
    b"Content-Length: 0\r\n"
    b"Content-Type: text/html\r\n"
    b"Access-Control-Allow-Origin: *\r\n"
    b"Access-Control-Allow-Methods: GET,PUT,POST\r\n"
    b"\r\n"
    b"0\r\n\r\n"
)


@dataclass
class FakeDevice:
    """Serves canned raw responses and records what it was asked for."""

    routes: dict[str, bytes] = field(default_factory=dict)
    requests: list[RecordedRequest] = field(default_factory=list)
    host: str = "127.0.0.1"
    port: int = 0
    _server: asyncio.AbstractServer | None = None

    def route(self, path: str, response: bytes) -> None:
        """Serve `response` for `path` (the part after /api/v1/)."""
        self.routes[path] = response

    @property
    def paths_requested(self) -> list[str]:
        return [r.path for r in self.requests]

    async def _handle(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            head = await reader.readuntil(b"\r\n\r\n")
        except (asyncio.IncompleteReadError, ConnectionError):
            writer.close()
            return

        lines = head.decode("latin-1").split("\r\n")
        method, target, _ = lines[0].split(" ", 2)
        headers = {}
        for line in lines[1:]:
            if ": " in line:
                name, value = line.split(": ", 1)
                headers[name.lower()] = value

        body = b""
        if (length := int(headers.get("content-length", 0))) > 0:
            body = await reader.readexactly(length)

        path = target.removeprefix("/api/v1/")
        self.requests.append(RecordedRequest(method, path, headers, body))

        writer.write(self.routes.get(path, status_response(404, "Not Found")))
        await writer.drain()
        writer.close()

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle, self.host, 0)
        self.port = self._server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
