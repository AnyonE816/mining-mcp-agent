# 矿权日报 Agent — 5 分钟启动指南

## 你需要准备

- **Python 3.11+**（或 Docker）
- **阿里云百炼 API Key**（免费注册: https://bailian.console.aliyun.com/）
  - 模型: qwen3-max，通过 DashScope OpenAI-compatible 接口调用
  - 新用户有免费额度，足够测试

## 1. 设置 API Key（二选一）

**方式一（推荐）：创建 .env 文件**

```bash
cd mining-mcp-agent
echo 'DASHSCOPE_API_KEY=sk-your-key-here' > .env
```

**方式二：环境变量**

```bash
export DASHSCOPE_API_KEY="sk-your-key-here"
```

Agent 启动时会先检查环境变量 `DASHSCOPE_API_KEY`，再检查项目根目录 `.env` 文件。两者都没找到会报错并给出提示。

## 2. 安装依赖

```bash
pip install -r requirements.txt
```

> 若 PyPI 慢，用清华镜像: `pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple`

## 3. 运行

```bash
python -m agent.client "给我生成一份关于 Pilbara 锂矿的今日简报"
```

Agent 运行流程：
1. 启动 3 个 MCP server 子进程（mining-news / lme-price / mineral-pdf）
2. 通过 stdio 连接，加载全部 5 个 tools
3. qwen3-max 自主决定调用哪些工具、以什么顺序调用
4. 综合所有工具返回结果，生成 Markdown 简报

## 4. Docker 运行

```bash
# 确保 .env 文件存在且包含 DASHSCOPE_API_KEY
docker-compose up --build

# 或传入环境变量
DASHSCOPE_API_KEY="sk-your-key" docker-compose up --build

# 自定义查询
docker-compose run --rm agent "分析铜矿市场近期趋势"
```

## 5. 接入 Claude Desktop（可选）

将 `mcp-config.json` 内容合并到 Claude Desktop 配置文件：

- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`

重启 Claude Desktop 后即可在对话中直接使用 3 个 MCP server。

## 项目结构

```
mining-mcp-agent/
├── servers/
│   ├── mining_news_mcp.py      # MCP Server 1: 新闻搜索
│   ├── mineral_pdf_mcp.py      # MCP Server 2: PDF 储量抽取
│   └── lme_price_mcp.py        # MCP Server 3: 价格查询
├── agent/
│   ├── client.py               # Agent 编排 (tool-calling loop)
│   └── prompts.py              # System prompt + 报告模板
├── shared/config.py            # 配置
├── mcp-config.json             # Claude Desktop 直连
├── docker-compose.yml + Dockerfile
├── .env.example                # API Key 配置模板
└── docs/
    ├── TECHNICAL_SPEC.md       # 技术规格
    └── COLLABORATION_LOG.md    # 开发协作记录
```

## 故障排查

| 问题 | 原因 | 解决 |
|------|------|------|
| `❌ 未找到 DASHSCOPE_API_KEY` | 未设置 API Key | 按上方"方式一"创建 `.env` 文件 |
| mining.com API 无响应 | 国内网络可能被墙 | 不影响价格和 PDF server，Agent 会在报告中说明 |
| 价格数据为 demo | akshare 当日无实时数据 | 自动使用 benchmark 估算值，接口设计支持替换实时源 |
| MCP server 启动失败 | mcp 包未安装 | `pip install mcp` |
