"""Allow-list CONNECT proxy for dependency installs: public PyPI/npm hosts on 443 only; everything else is refused."""
import asyncio
import json
import sys

from runner.commands import TOOL_POLICY

REGISTRY_PORT = 443
BUFFER = 65536


def parse_connect(line):
    """Return (host, port) from a `CONNECT host:port HTTP/1.x` request line, or None when it is anything else."""
    parts = line.strip().split(" ")
    if len(parts) != 3 or parts[0] != "CONNECT" or not parts[2].startswith("HTTP/1.") or parts[1].count(":") != 1:
        return None
    host, port = parts[1].split(":")
    return (host.lower(), int(port)) if port.isdigit() else None


def target_allowed(target):
    return target is not None and target[0] in TOOL_POLICY["registry_hosts"] and target[1] == REGISTRY_PORT


def log(**fields):
    print(json.dumps(fields, sort_keys=True), file=sys.stdout, flush=True)


async def pipe(reader, writer):
    try:
        while data := await reader.read(BUFFER):
            writer.write(data)
            await writer.drain()
    finally:
        writer.close()


async def handle(reader, writer):
    target = parse_connect((await reader.readline()).decode(errors="replace"))
    while (await reader.readline()).strip():
        pass  # drop request headers
    if not target_allowed(target):
        log(event="refused", target=list(target) if target else None)
        writer.write(b"HTTP/1.1 403 Forbidden\r\n\r\n")
        await writer.drain()
        writer.close()
        return
    try:
        upstream_reader, upstream_writer = await asyncio.open_connection(*target)
    except OSError:
        writer.write(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
        await writer.drain()
        writer.close()
        return
    log(event="tunnel", target=list(target))
    writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
    await writer.drain()
    await asyncio.gather(pipe(reader, upstream_writer), pipe(upstream_reader, writer), return_exceptions=True)


async def main(host="127.0.0.1", port=3128):  # bind address is an operator choice; never a public interface
    server = await asyncio.start_server(handle, host, port)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
