# COLLABORATION_LOG.md — 人机协作开发记录

## 2026-06-24 · 项目初始化

### 决策：官方 mcp SDK vs 手写协议
- **选型**：官方 `mcp` 包 1.28.0 + FastMCP
- **理由**：面试项目，用官方 SDK 体现对 MCP 生态的理解。stdio transport 本地调试方便。
- **风险**：v2 是 alpha，我们锁定 v1.x 稳定版。

### 决策：Agent 编排不用 LangChain
- **选型**：手写 tool-calling loop
- **理由**：
  1. SmartSweep 项目教训——LangChain Agent 引入额外抽象层，和 MCP 协议叠加造成概念混乱
  2. MCP 本身就是 tool 发现和调用的标准协议，Agent 只需收集 tools → 喂 LLM → 执行
  3. 约 80 行代码搞定，比 LangChain 几十行配置更透明
- **权衡**：失去 LangChain 的回调/追踪生态，但对 demo 项目不重要。

### 决策：单容器 Docker
- **选型**：一个 Dockerfile，agent 启动时 spawn 3 个 MCP server 子进程
- **理由**：
  1. stdio transport 需要父子进程关系，多容器反而复杂
  2. 5 分钟跑起来的要求，单容器最可靠
  3. docker-compose 仍然提供（单服务），满足题目要求
- **权衡**：不是"微服务"架构，但对 demo 是正确选择。

### 决策：锂价格数据源
- **选型**：akshare 覆盖 LME 铜锌镍 + demo fallback 覆盖锂
- **理由**：
  1. akshare 无直接锂精矿（spodumene concentrate）接口
  2. yfinance 在中国被墙
  3. 锂精矿价格为基准价（Benchmark Mineral Intelligence / Fastmarkets），免费 API 不可得
  4. 接口设计通用（`get_price("lithium", ...)`），数据源可后续替换
  5. demo fallback 基于 Argus/Fastmarkets 公开报价，确保可跑
- **注意**：用户指出 Pilbara 锂矿是锂辉石精矿（spodumene），不是碳酸锂（LC0），数据源需匹配。

### 项目结构设计原则（吸取 SmartSweep 教训）
1. **不搞模块级单例**：依赖在入口函数传参注入，不在 import 时初始化
2. **不搞只有一个实现的抽象类**：MCP 协议本身就是接口，不需要工厂模式
3. **不拆碎配置文件**：一个 .env + 代码内 prompt 常量，不用 4 个 YAML
4. **不复制粘贴函数**：一个参数化函数替代 n 个相似函数
5. **每个 server 独立可运行**：`python servers/xxx_mcp.py` 即可启动，不依赖 agent

---

## 2026-06-24 · 端到端测试

### 测试 1: Server 导入验证
- mining-news: 2 tools (search, fetch_article) ✅
- lme-price: 2 tools (get_price, get_trend) ✅
- mineral-pdf: 1 tool (extract_resources) ✅

### 测试 2: 数据源验证
- mining-news.search("lithium", 7): 返回 10 条真实结果 ✅ (mining.com WP API 正常)
- lme-price.get_price("lithium"): demo 数据返回 ✅
- lme-price.get_price("copper"): demo 数据返回 ✅ (akshare 当日无数据)

### 测试 3: 全流程 Agent
- 查询: "给我生成一份关于 Pilbara 锂矿的今日简报"
- 结果: ✅ 4 轮 LLM 推理, 调用 3 次 search + 1 次 get_price + 1 次 get_trend
- 输出: 完整 Markdown 中文简报 (5 段结构)
- LLM 行为: 搜索无 Pilbara 特定结果时诚实声明, 未编造数据

### 发现 & 修复
- LITHIUM_TREND 日期年份错误 (2025→2026): 导致 30 天趋势返回空, 已修复
- akshare 铜锌镍当日无实时数据: demo fallback 生效, 符合设计

### 已知限制
1. mining.com 新闻多为英文, LLM 需自行翻译摘要
2. 锂精矿价格为 demo 数据, 非实时
3. mineral-pdf server 依赖外部 PDF URL, 无内置示例
4. 报告质量依赖 LLM 推理能力 (qwen3-max), 不同模型结果有差异

---

## 2026-06-24 · 移除 Demo 模式

### 决策：不搞规则引擎 demo
- **用户反馈**："demo 模型是假的模型调用，直接背离模型思考的主题了"
- **用户判断正确**: 面试官要看的是 LLM 通过 MCP 协议智能编排工具调用, 不是 if-else 规则匹配
- **最终方案**: 只保留 LLM 模式, 无 API Key 时清晰报错并指引获取

### 决策：API Key 获取策略
- `.env` 文件 + 环境变量双通道, `_load_api_key()` 先读 env var 再读 .env
- 企业面试官大概率已有阿里云账号, DashScope 免费注册即可
- RUN.md 首段明确说明需要准备什么, 给出注册链接
