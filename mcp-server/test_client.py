"""Smoke test: talk to the MCP server over stdio like a real client."""

import asyncio
import json
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

TEST_MODEL = "kokoro"
TEST_TEXT = "Hello from the MCP smoke test."


async def main() -> None:
    params = StdioServerParameters(
        command=sys.executable, args=["server.py"], env=None
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            names = sorted(t.name for t in tools.tools)
            print("tools:", names)
            assert names == [
                "generate_audio", "list_models", "play_audio",
                "start_model", "stop_model",
            ], names

            result = await session.call_tool("list_models", {})
            models = json.loads(result.content[0].text)
            print("models:", [m["name"] for m in models])
            assert len(models) == 9, len(models)

            target = next(m for m in models if m["name"] == TEST_MODEL)
            if target["status"] != "running":
                result = await session.call_tool(
                    "start_model", {"name": TEST_MODEL}
                )
                print("start:", result.content[0].text)

            result = await session.call_tool(
                "generate_audio",
                {"model": TEST_MODEL, "params": {"input": TEST_TEXT},
                 "output_name": "mcp-smoke-test"},
            )
            assert not result.is_error, result.content[0].text
            out = json.loads(result.content[0].text)
            print("generated:", out)
            assert out["bytes"] > 1000, out

            # play_audio: on a machine with speakers this plays the clip;
            # on a headless host it must fail with a clear explanation.
            result = await session.call_tool(
                "play_audio", {"path": out["path"]}
            )
            text = result.content[0].text
            if result.is_error:
                assert "No audio player found" in text, text
                print("play_audio: no player on this host (expected on a server)")
            else:
                print("play_audio:", text)

    print("SMOKE TEST PASSED")


if __name__ == "__main__":
    asyncio.run(main())
