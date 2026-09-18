"""Loopback TCP proxy with controlled latency and connection kills.

Forwards 127.0.0.1:PROXY_PORT to a running loopback deployment so weak-network
behavior can be measured against real HTTP traffic. A tiny control endpoint
adjusts behavior at runtime:

  POST /config {"latency_ms": 300}                 delay every chunk both ways
  POST /config {"kill_path": "/api/v1/cooking", "kill_after_ms": 300,
                "kill_count": 1}                   abort matching requests after
                                                   the server had time to process
  POST /config {"kill_path": "/api/v1/agent/runs/x/events",
                "kill_mode": "stream", "kill_after_ms": 1200,
                "kill_count": 1}                   relay the response, then abort
                                                   mid-stream when the timer fires
                                                   (default kill_mode "request" never
                                                   relays the killed response)
  GET  /stats                                      per-request log (no bodies)

Requests and responses are parsed per HTTP/1.1 message, so kills also apply to
requests on reused keep-alive connections. Responses without a framing length
(SSE streams) are relayed until the server closes the stream. Upstream
connections closed by the server while idle are replaced transparently, like a
real reverse proxy, instead of stranding the next request.

Never bind this beyond loopback; it is a fault-injection tool, not a proxy for
untrusted traffic.
"""

import argparse
import asyncio
import json
import time

CONFIG = {"latency_ms": 0, "kill_path": None, "kill_after_ms": 300, "kill_count": 0,
          "kill_mode": "request"}
EVENTS = []
METHODS = (b"GET ", b"POST ", b"PUT ", b"DELETE ", b"PATCH ", b"HEAD ", b"OPTIONS ")


async def delay():
    ms = CONFIG["latency_ms"]
    if ms:
        await asyncio.sleep(ms / 1000)


async def read_message(reader, buffered):
    data = buffered
    while b"\r\n\r\n" not in data:
        chunk = await reader.read(65536)
        if not chunk:
            return None
        data += chunk
    head, _, rest = data.partition(b"\r\n\r\n")
    length = 0
    for header in head.split(b"\r\n")[1:]:
        if header.lower().startswith(b"content-length:"):
            length = int(header.split(b":", 1)[1])
    while len(rest) < length:
        chunk = await reader.read(65536)
        if not chunk:
            return None
        rest += chunk
    return head + b"\r\n\r\n" + rest[:length], rest[length:], head


async def relay_response(s_reader, writer, deadline=None):
    """Relay one response; return False when a stream deadline cut it short."""
    first = await s_reader.read(65536)
    if not first:
        return True
    if b"\r\n\r\n" not in first:
        head = first
        while b"\r\n\r\n" not in head:
            more = await s_reader.read(65536)
            if not more:
                await delay()
                writer.write(head)
                await writer.drain()
                return True
            head += more
    else:
        head = first
    raw_head, _, body = head.partition(b"\r\n\r\n")
    await delay()
    writer.write(head)
    await writer.drain()
    fields = raw_head.split(b"\r\n")[1:]
    content_length = None
    chunked = False
    for header in fields:
        lower = header.lower()
        if lower.startswith(b"content-length:"):
            content_length = int(lower.split(b":", 1)[1])
        elif lower.startswith(b"transfer-encoding:") and b"chunked" in lower:
            chunked = True
    status = raw_head.split(b" ", 2)[1] if raw_head.startswith(b"HTTP/") else b""
    if status in (b"204", b"304") or content_length == 0:
        return True
    if deadline is not None and time.monotonic() >= deadline:
        return False
    if content_length is not None:
        remaining = content_length - len(body)
        while remaining > 0:
            chunk = await s_reader.read(min(65536, remaining))
            if not chunk:
                return True
            remaining -= len(chunk)
            await delay()
            writer.write(chunk)
            await writer.drain()
            if deadline is not None and time.monotonic() >= deadline:
                return False
        return True
    if chunked:
        tail = body[-5:]
        while not tail.endswith(b"0\r\n\r\n"):
            chunk = await s_reader.read(65536)
            if not chunk:
                return True
            tail = (tail + chunk)[-5:]
            await delay()
            writer.write(chunk)
            await writer.drain()
            if deadline is not None and time.monotonic() >= deadline:
                return False
        return True
    while True:
        chunk = await s_reader.read(65536)
        if not chunk:
            return True
        await delay()
        writer.write(chunk)
        await writer.drain()
        if deadline is not None and time.monotonic() >= deadline:
            return False


async def handle(reader, writer, target_host, target_port):
    peer = writer.get_extra_info("peername")
    s_reader = s_writer = None
    buffered = b""
    try:
        while True:
            started = time.monotonic()
            message = await read_message(reader, buffered)
            if message is None:
                return
            request, buffered, head = message
            request_line = head.split(b"\r\n", 1)[0]
            path = request_line.split(b" ", 2)[1].decode("latin1") if request_line.startswith(METHODS) else "?"
            # The upstream (nginx) closes idle keep-alive connections on its own
            # schedule; a request forwarded into that half-closed socket is
            # silently lost, so reconnect transparently like a real reverse
            # proxy would.
            if s_reader is None or s_reader.at_eof():
                if s_writer is not None:
                    s_writer.close()
                try:
                    s_reader, s_writer = await asyncio.open_connection(target_host, target_port)
                except ConnectionError:
                    writer.close()
                    return
            await delay()
            s_writer.write(request)
            await s_writer.drain()
            if (CONFIG["kill_path"] and CONFIG["kill_count"] > 0
                    and CONFIG["kill_path"].encode() in request_line):
                CONFIG["kill_count"] -= 1
                if CONFIG.get("kill_mode") == "stream":
                    deadline = time.monotonic() + CONFIG["kill_after_ms"] / 1000
                    completed = await relay_response(s_reader, writer, deadline=deadline)
                    EVENTS.append({"path": path, "killed": not completed, "mode": "stream",
                                   "peer": f"{peer[0]}:{peer[1]}",
                                   "seconds": round(time.monotonic() - started, 3)})
                    return
                await asyncio.sleep(CONFIG["kill_after_ms"] / 1000)
                EVENTS.append({"path": path, "killed": True, "mode": "request",
                               "peer": f"{peer[0]}:{peer[1]}",
                               "seconds": round(time.monotonic() - started, 3)})
                return
            await relay_response(s_reader, writer)
            EVENTS.append({"path": path, "killed": False, "latency_ms": CONFIG["latency_ms"],
                           "seconds": round(time.monotonic() - started, 3)})
    except (ConnectionError, asyncio.IncompleteReadError, asyncio.TimeoutError):
        return
    finally:
        try:
            writer.close()
            s_writer.close()
        except ConnectionError:
            pass


async def control(reader, writer):
    data = b""
    while b"\r\n\r\n" not in data:
        chunk = await reader.read(65536)
        if not chunk:
            writer.close()
            return
        data += chunk
    line, _, body = data.partition(b"\r\n\r\n")
    length = 0
    for header in line.split(b"\r\n")[1:]:
        if header.lower().startswith(b"content-length:"):
            length = int(header.split(b":", 1)[1])
    while len(body) < length:
        body += await reader.read(65536)
    if line.startswith(b"POST /config"):
        CONFIG.update(json.loads(body.decode()))
        payload = json.dumps({"config": {k: v for k, v in CONFIG.items()}}).encode()
    elif line.startswith(b"GET /stats"):
        payload = json.dumps({"events": EVENTS[-200:]}).encode()
    elif line.startswith(b"POST /reset"):
        EVENTS.clear()
        payload = b'{"reset": true}'
    else:
        payload = b'{"error": "unknown control route"}'
    writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: "
                 + str(len(payload)).encode() + b"\r\n\r\n" + payload)
    await writer.drain()
    writer.close()


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--listen", type=int, default=18083)
    parser.add_argument("--control", type=int, default=18084)
    parser.add_argument("--target-host", default="127.0.0.1")
    parser.add_argument("--target-port", type=int, default=18082)
    args = parser.parse_args()
    proxy = await asyncio.start_server(lambda r, w: handle(r, w, args.target_host, args.target_port),
                                       "127.0.0.1", args.listen)
    ctl = await asyncio.start_server(control, "127.0.0.1", args.control)
    print(f"proxy 127.0.0.1:{args.listen} -> {args.target_host}:{args.target_port}, "
          f"control on 127.0.0.1:{args.control}")
    async with proxy, ctl:
        await asyncio.gather(proxy.serve_forever(), ctl.serve_forever())


if __name__ == "__main__":
    asyncio.run(main())
