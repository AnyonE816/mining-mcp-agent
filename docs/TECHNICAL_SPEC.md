# 矿权日报 Agent — 技术规格文档

## 架构

```
User Query (自然语言)
       │
       ▼
┌──────────────────────────────────────┐
│           Agent Client (agent/)       │
│                                      │
│  1. Spawn 3 MCP server 子进程        │
│  2. 收集所有 tools → OpenAI format   │
│  3. Tool-calling loop:               │
│     LLM ⇄ MCP tool execution         │
│  4. 生成 Markdown 简报               │
└──────┬──────────┬──────────┬─────────┘
       │ stdio    │ stdio    │ stdio
       ▼          ▼          ▼
┌──────────┐ ┌──────────┐ ┌──────────┐
│ mining-  │ │ lme-     │ │ mineral- │
│ news-mcp │ │ price-mcp│ │ pdf-mcp  │
│          │ │          │ │          │
│ search   │ │get_price │ │extract_  │
│ fetch_   │ │get_trend │ │resources │
│ article  │ │          │ │          │
└──────────┘ └──────────┘ └──────────┘
```

## MCP 协议实现

### Transport
- 全部使用 **stdio** transport（JSON-RPC over stdin/stdout）
- Agent 作为父进程，spawn 3 个 server 子进程
- 子进程生命周期 = Agent 生命周期

### Server 实现
每个 server 使用官方 `mcp` SDK 的 `FastMCP`：
- `@mcp.tool()` 装饰器注册工具
- 函数签名自动推导 JSON Schema
- `mcp.run(transport="stdio")` 启动

### Client 实现
- `StdioServerParameters` 指定子进程启动命令
- `stdio_client()` 建立 stdio 通道
- `ClientSession` 管理会话（initialize → list_tools → call_tool）
- `AsyncExitStack` 管理多 session 生命周期

### Tool 命名空间
MCP tool 名称不带 server 前缀。Agent 在收集时加前缀避免冲突：
- `mining-news.search`
- `mining-news.fetch_article`
- `lme-price.get_price`
- `lme-price.get_trend`
- `mineral-pdf.extract_resources`

## LLM 编排

### Model
- qwen3-max via DashScope OpenAI-compatible API
- endpoint: `https://dashscope.aliyuncs.com/compatible-mode/v1`

### Tool-calling Loop
```
for iteration in 1..MAX(10):
    response = LLM.chat(messages, tools)
    if no tool_calls:
        return response.content  # 最终报告

    for each tool_call:
        server, tool = parse_name(tool_call.function.name)
        result = MCP.call_tool(server, tool, args)
        messages.append(tool_result)
```

### System Prompt
中文 prompt，定义 Agent 角色、工作流程、报告模板。详见 `agent/prompts.py`。

## 数据源

| Server | Tool | 数据源 | 类型 |
|--------|------|--------|------|
| mining-news | search | mining.com WP REST API | 实时 |
| mining-news | fetch_article | HTTP GET + BeautifulSoup | 实时 |
| lme-price | get_price/get_trend | akshare (铜锌镍) + demo (锂) | 混合 |
| mineral-pdf | extract_resources | pdfplumber | 实时 |

### 锂电池价格说明
锂辉石精矿（spodumene concentrate 6% Li2O）价格无免费实时 API。
当前使用 demo 数据（基于 Argus/Fastmarkets 公开评估价）。
`get_price("lithium")` 接口通用，后续可替换为实时数据源。

## 报告输出格式

```markdown
# 矿权日报：[主题] ([日期])

## 一、市场新闻摘要
## 二、资源储量概况
## 三、价格行情
## 四、风险提示
## 五、数据来源
```

## 错误处理策略

- MCP server 不可用 → Agent 启动时报错，不继续
- Tool 执行失败 → 返回 `{"error": "..."}` 给 LLM，LLM 自行判断是否重试或跳过
- 数据源无数据 → 返回提示信息，LLM 在报告中诚实声明
- LLM API 错误 → 向上抛出，终止运行

## 依赖

```
mcp>=1.20          # MCP Python SDK (官方)
httpx>=0.27        # HTTP client
beautifulsoup4     # HTML 解析
lxml>=5.0          # HTML parser
akshare>=1.15      # 金融数据
pdfplumber>=0.11   # PDF 表格抽取
dashscope>=1.20    # 阿里云 LLM SDK
openai>=1.0        # OpenAI-compatible client
pydantic-settings  # 配置管理
```
