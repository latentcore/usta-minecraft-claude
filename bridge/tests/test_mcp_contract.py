"""MCP sozlesme testleri (Q8): araclar listelenir, semalar gecerli, oyun kapaliyken anlasilir mesaj, sonuc boyutlari sinirda."""
import asyncio
import json
import os
import sys
import time
from pathlib import Path

import jsonschema
import pytest
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

BRIDGE = Path(__file__).resolve().parents[1]


def _params(game_dir: str) -> StdioServerParameters:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("CLAUDE", "ANTHROPIC"))}
    env["USTA_GAME_DIR"] = game_dir
    env["PYTHONPATH"] = str(BRIDGE)
    return StdioServerParameters(command=sys.executable, args=["-m", "usta.mcp_server"], env=env, cwd=str(BRIDGE))


async def _run(game_dir, fn):
    async with stdio_client(_params(game_dir)) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            return await fn(s)


def test_tools_listed_and_schemas_valid(tmp_path):
    async def fn(s):
        return await s.list_tools()
    res = asyncio.run(_run(str(tmp_path), fn))
    names = [t.name for t in res.tools]
    assert len(names) >= 30, names
    for t in res.tools:
        jsonschema.Draft202012Validator.check_schema(t.input_schema if hasattr(t, "input_schema") else t.inputSchema)
        assert t.description and len(t.description) > 20


def test_game_closed_message(tmp_path):
    async def fn(s):
        t0 = time.time()
        r = await s.call_tool("get_status", {})
        r2 = await s.call_tool("get_context", {})
        return r, r2, time.time() - t0
    r, r2, dt = asyncio.run(_run(str(tmp_path), fn))
    txt = r.content[0].text
    assert "closed" in txt and "açık değil" in json.loads(txt)["message"]
    assert "açık değil" in json.loads(r2.content[0].text)["message"]
    assert dt < 3.0
