# ASIN PriceLens 价格透镜

**批量抓取 Amazon 17 个站点的 ASIN 本地原生价格,生成可交互 HTML 洞察报告 + CSV 明细。**

AST 内部工具 · 与 VPN 状态无关 · 不依赖内部 API

---

## 安装

```bash
git clone ssh://git.amazon.com:2222/pkg/PriceLens && cd PriceLens && pip install -e .
```

安装后 `pricelens` 命令即可全局使用。Python >= 3.9。

---

## 快速开始

### 从文件输入(推荐)

```bash
pricelens --markets AU --input asins.xlsx --output ./report --yes
```

### 直接指定 ASIN

```bash
pricelens --markets DE,UK,US --asins B0DCBB2YTR,B09B96TG33 --output ./report --yes
```

### 带标题和日期范围

```bash
pricelens --markets AU --input data.xlsx --title "AU Security Camera" --subtitle "2026.5.1 – 7.31" --output ./report --yes
```

---

## 支持的 17 个市场

| 代码 | 站点 | 币种 | 代码 | 站点 | 币种 |
|------|------|------|------|------|------|
| US | amazon.com | USD | JP | amazon.co.jp | JPY |
| UK | amazon.co.uk | GBP | CA | amazon.ca | CAD |
| DE | amazon.de | EUR | AU | amazon.com.au | AUD |
| FR | amazon.fr | EUR | AE | amazon.ae | AED |
| IT | amazon.it | EUR | SA | amazon.sa | SAR |
| ES | amazon.es | EUR | SG | amazon.sg | SGD |
| NL | amazon.nl | EUR | IN | amazon.in | INR |
| SE | amazon.se | SEK | MX | amazon.com.mx | MXN |
| PL | amazon.pl | PLN | BR | amazon.com.br | BRL |
|    |            |     | TR | amazon.com.tr | TRY |

### 常用组合

- **EU5** → `DE,FR,IT,ES,UK`
- **NA** → `US,CA,MX`
- **APAC** → `JP,SG,IN,AU`
- **全欧** → `DE,FR,IT,ES,UK,NL,SE,PL`
- **全量 19 站** → `US,UK,DE,FR,IT,ES,NL,SE,PL,JP,CA,AU,AE,SA,SG,IN,MX,BR,TR`

---

## 输入格式

支持 `.xlsx`、`.csv`、`.tsv`、`.txt`。自动检测以下列(有就加,没有就忽略):

| 列名关键词 | 说明 |
|-----------|------|
| ASIN | 必须。10 位字母数字 |
| Search Rank | 搜索排名(数字) |
| Purchase Rank | 购买排名(数字) |
| Keyword Searches / Search Volume | 搜索量快照(单值) |
| YYYY-MM 格式表头 | 月度搜索量时间序列 |

**示例 Excel 结构:**

| ASIN | Search Rank | Purchase Rank | Keyword Searches |
|------|-------------|---------------|-----------------|
| B0CDCL38KZ | 1 | 1 | 5878 |
| B0CLRNPYD4 | 2 | 3 | 4422 |

---

## 输出报告

每次运行生成两个带时间戳的文件:

- `asin_prices_YYYYMMDD_HHMMSS.csv` — 原始明细
- `asin_prices_YYYYMMDD_HHMMSS.html` — 可交互报告

### HTML 报告包含

1. **市场 Tab 切换** — 多市场时按 tab 查看
2. **KPI 卡片** — 成功抓取数、最低/最高/中位价、品牌数
3. **Price Segments 图** — 智能分档(3 或 4 档,自适应价差)
4. **Top Brands 图** — 品牌分布柱状图
5. **Search Volume by ASIN (Top 30)** — 搜索量柱状图(如有数据)
6. **Volume Trend 折线图** — 月度趋势(如有时间序列数据)
7. **明细表** — 每列支持排序 ↕ + 筛选 ▾(数值范围 / 文本多选)

---

## CLI 完整参数

```
pricelens [OPTIONS]

必选:
  --markets, -m    逗号分隔的市场代码 (如 AU,US,DE)
  --input, -i      输入文件路径 (xlsx/csv/tsv/txt)
  --asins, -a      或直接逗号分隔 ASIN (与 --input 二选一)

可选:
  --output, -o     输出目录 (默认当前目录)
  --title          报告标题 (默认 "ASIN Price Intelligence Report")
  --subtitle       标题下方副标题,如日期范围
  --workers, -w    每个市场的并发线程数 (默认 6)
  --delay          请求间隔秒数 (默认 0.4)
  --yes, -y        跳过确认提示直接运行
  --version        显示版本号
```

---

## 性能 & 限流

| 请求量 | 预计耗时 | 建议 |
|--------|---------|------|
| ≤ 30 | 1–2 分钟 | 默认参数即可 |
| 30–100 | 3–8 分钟 | 默认参数即可 |
| 100–300 | 15–40 分钟 | Amazon 会逐步限流 |
| > 300 | 较长 | 用 `--delay 1.0 --workers 3` 慢跑 |

Amazon 在连续请求 ~50 次后会开始限流(响应变慢但不会封禁),工具会自动重试。

---

## 技术原理

```
用户 (任意 IP/VPN) → pricelens CLI
  ↓
1. GET amazon.{tld}/ — 获取 session cookies
2. POST /portal-migration/hz/glow/address-change — 注入本地邮编
3. Set-Cookie: i18n-prefs={本地币种} — 强制本地币种
4. GET /dp/{ASIN}?th=1 — 抓取产品页 → 解析价格/品牌/标题
  ↓
输出: HTML 报告 + CSV
```

**核心洞察**: Amazon 按 delivery address(而非 IP)决定展示什么价格。通过 cookie 注入本地邮编 + 币种,无论用户在哪里,都能拿到目标市场的本地原生价格。

---

## 品牌识别逻辑

1. **Title 首词优先** — Amazon 惯例:标题第一个词就是品牌(如 "Tapo 2K Security Camera")
2. **智能双词** — 第二个词是 Security/Basics/Home 等后缀时自动合并(如 "eufy Security")
3. **Storefront 兜底** — Title 识别失败时回退到 byline/storefront/JSON

---

## 智能价格分档

- 价差 < 3× → **3 档**:Entry / Mid-tier / Premium
- 价差 > 5× 且样本 ≥ 20 → **4 档**:Entry / Mainstream / Premium / Flagship
- 样本 ≥ 12 用分位数切分,< 12 用等宽切分

---

## 与 AI Agent 集成

本工具设计为 CLI-first,任何 AI agent 都可以直接调用:

| Agent | 集成方式 |
|-------|---------|
| Orcha | Shell tool 调用 `pricelens ...`,已有 skill 文件 |
| Claude Code | Bash tool 调用,已有 skill 文件 |
| Kiro / Cursor | Terminal 命令调用 |
| 人工 | 直接在终端运行 |

Skill 文件位于 `skills/orcha/` 和 `skills/claude-code/` 目录下。

---

## 合规提醒

- ⚠️ **仅限 AST 内部使用**
- 不包含任何内部 API 调用,全部基于公开前端页面
- 分享给客户前,使用 Peer Benchmarking 匿名化框架,**不得点名具体竞品**
- 不得将 DSP revenue 和 SA sales 混合计算

---

## 常见问题

**Q: 为什么有些 ASIN 显示 `not_found`?**
A: 该 ASIN 在目标市场不存在(正常现象,如 Amazon Device 仅在部分市场售卖)。

**Q: 为什么价格为空但状态是 `ok`?**
A: 极少数情况下 Amazon 页面渲染了 display_price 但未嵌入 JSON 数值。CSV 中 display_price 列仍有值。

**Q: 需要开 VPN 吗?**
A: **不需要**。工具通过 cookie 注入 delivery address,与你的网络出口 IP 无关。

**Q: 大批量跑一半报错了怎么办?**
A: 加大延迟重跑:`pricelens --delay 1.5 --workers 3 ...`

---

## 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| 1.1.0 | 2026-08-05 | reporter.py 完整重写(白底主题、Search Volume 柱状图、smart banding);新增 `--subtitle` 参数 |
| 1.0.0 | 2026-08-04 | 首版发布,17 市场支持,品牌识别,HTML 报告 |
