"""Agent Client — MCP 多服务器编排 + LLM tool-calling loop.

连接 3 个 MCP server (mining-news, mineral-pdf, lme-price) 通过 stdio,
收集 tools, 使用 qwen3-max (DashScope) 运行 tool-calling loop,
生成矿权日报 Markdown 简报.

Usage:
    python -m agent.client "给我生成一份关于 Pilbara 锂矿的今日简报"

前置条件:
    DASHSCOPE_API_KEY 环境变量 或 项目根目录 .env 文件中设置
"""

import asyncio
import contextlib
import json
import os
import sys
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from agent.prompts import SYSTEM_PROMPT

# ---------------------------------------------------------------------------
# Server definitions
# ---------------------------------------------------------------------------
SERVERS_DIR = Path(__file__).parent.parent / "servers"

SERVERS = {
    "mining-news": str(SERVERS_DIR / "mining_news_mcp.py"),
    "lme-price": str(SERVERS_DIR / "lme_price_mcp.py"),
    "mineral-pdf": str(SERVERS_DIR / "mineral_pdf_mcp.py"),
}

MAX_ITERATIONS = 10

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_api_key() -> str:
    """Load DASHSCOPE_API_KEY: env var first, then .env file, then fail."""
    key = os.getenv("DASHSCOPE_API_KEY", "").strip()
    if key:
        return key

    # Try .env file in project root
    env_file = SERVERS_DIR.parent / ".env"
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line.startswith("DASHSCOPE_API_KEY="):
                    val = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if val and val != "sk-your-key-here":
                        return val

    return ""


def _mcp_to_openai_tools(tools, server_name: str) -> list[dict]:
    """Convert MCP tool schemas to OpenAI function-calling tool definitions."""
    result = []
    for tool in tools:
        result.append({
            "type": "function",
            "function": {
                "name": f"{server_name}.{tool.name}",
                "description": tool.description or "",
                "parameters": tool.inputSchema if tool.inputSchema else {"type": "object", "properties": {}},
            },
        })
    return result


async def _call_tool(session: ClientSession, tool_name: str, args: dict) -> str:
    """Call an MCP tool and return text content.

    Handles both single-block and multi-block responses:
    - Single block → return as-is
    - Multiple blocks → wrap as JSON array
    """
    try:
        result = await session.call_tool(tool_name, args)
        texts = []
        for block in result.content:
            if hasattr(block, "text"):
                texts.append(block.text)
        if len(texts) == 0:
            return str(result.content)
        if len(texts) == 1:
            return texts[0]
        return "[" + ",".join(texts) + "]"
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Agent core
# ---------------------------------------------------------------------------

async def run_agent(query: str, api_key: str) -> str:
    """Connect to MCP servers, run tool-calling loop, return Markdown report."""
    from openai import OpenAI

    base_url = os.getenv("LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    model = os.getenv("LLM_MODEL", "qwen3-max")
    llm = OpenAI(api_key=api_key, base_url=base_url)

    async with contextlib.AsyncExitStack() as stack:
        # --- Connect to all 3 MCP servers ---
        sessions: dict[str, ClientSession] = {}
        all_tools: list[dict] = []

        for server_name, server_path in SERVERS.items():
            print(f"  Connecting to {server_name}...", file=sys.stderr)
            params = StdioServerParameters(command=sys.executable, args=[server_path])
            read, write = await stack.enter_async_context(stdio_client(params))
            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()

            sessions[server_name] = session
            mcp_tools = (await session.list_tools()).tools
            all_tools.extend(_mcp_to_openai_tools(mcp_tools, server_name))
            print(f"  {server_name}: {len(mcp_tools)} tools loaded", file=sys.stderr)

        print(f"  Total: {len(all_tools)} tools across {len(sessions)} servers\n", file=sys.stderr)

        # --- Tool-calling loop ---
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": query},
        ]

        for iteration in range(1, MAX_ITERATIONS + 1):
            response = llm.chat.completions.create(
                model=model,
                messages=messages,
                tools=all_tools,
                tool_choice="auto",
            )
            msg = response.choices[0].message

            if not msg.tool_calls:
                print(f"  Report generated in {iteration} LLM round(s)", file=sys.stderr)
                return msg.content or ""

            print(f"  Round {iteration}: {len(msg.tool_calls)} tool call(s)", file=sys.stderr)
            messages.append(msg)

            for tc in msg.tool_calls:
                server_name, tool_name = tc.function.name.split(".", 1)
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}

                print(f"    → {tc.function.name}({json.dumps(args, ensure_ascii=False)})", file=sys.stderr)
                text = await _call_tool(sessions[server_name], tool_name, args)
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": text})

        return "Error: Agent exceeded maximum iterations without generating a report."


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

API_KEY_HELP = """
❌ 未找到 DASHSCOPE_API_KEY

本 Agent 使用阿里云百炼 (DashScope) 的 qwen3-max 模型进行智能编排。
请通过以下任一方式提供 API Key：

  方式一（推荐）：在项目根目录创建 .env 文件
    cd mining-mcp-agent
    echo 'DASHSCOPE_API_KEY=sk-your-key-here' > .env

  方式二：设置环境变量
    export DASHSCOPE_API_KEY="sk-your-key-here"

免费注册获取 API Key: https://bailian.console.aliyun.com/
"""


async def main():
    if len(sys.argv) < 2:
        print("Usage: python -m agent.client '<your query>'")
        print('Example: python -m agent.client "给我生成一份关于 Pilbara 锂矿的今日简报"')
        sys.exit(1)

    api_key = _load_api_key()
    if not api_key:
        print(API_KEY_HELP, file=sys.stderr)
        sys.exit(1)

    query = " ".join(sys.argv[1:])
    print(f"Query: {query}", file=sys.stderr)
    print(f"Model: {os.getenv('LLM_MODEL', 'qwen3-max')}\n", file=sys.stderr)

    report = await run_agent(query, api_key)
    print("\n" + "=" * 60)
    print(report)


if __name__ == "__main__":
    asyncio.run(main())
