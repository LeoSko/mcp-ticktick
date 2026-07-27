from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal

from fastmcp import FastMCP

from ticktick_mcp.auth import load_credentials
from ticktick_mcp.client import TickTickClient


@asynccontextmanager
async def lifespan(server: FastMCP) -> AsyncIterator[dict]:
    stored = load_credentials()
    access_token = os.environ.get("TICKTICK_ACCESS_TOKEN") or stored.get("access_token")
    if not access_token:
        raise RuntimeError(
            "TickTick authentication required. Run `mcp-ticktick login` or set "
            "TICKTICK_ACCESS_TOKEN."
        )
    client = TickTickClient(
        access_token=access_token,
        client_id=os.environ.get("TICKTICK_CLIENT_ID") or stored.get("client_id"),
        client_secret=os.environ.get("TICKTICK_CLIENT_SECRET") or stored.get("client_secret"),
        session_token=os.environ.get("TICKTICK_V2_SESSION_TOKEN"),
        refresh_token=os.environ.get("TICKTICK_REFRESH_TOKEN") or stored.get("refresh_token"),
    )
    async with client:
        yield {"client": client}


mcp = FastMCP("TickTick", lifespan=lifespan)

# Register tool and resource modules
from ticktick_mcp.resources import register_resources  # noqa: E402
from ticktick_mcp.tools import register_tools  # noqa: E402

register_tools(mcp)
register_resources(mcp)


def main(
    transport: Literal["stdio", "http", "streamable-http", "sse"] = "stdio",
    host: str = "127.0.0.1",
    port: int = 8000,
) -> None:
    if transport == "stdio":
        mcp.run(transport=transport)
        return
    mcp.run(transport=transport, host=host, port=port)


if __name__ == "__main__":
    main()
