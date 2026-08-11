# ASIN PriceLens 价格透镜

**批量抓取 Amazon 17 个站点的 ASIN 本地原生价格,生成可交互 HTML 洞察报告 + Excel 明细。**

AST 内部工具 · 与 VPN 状态无关 · 不依赖内部 API

---

## 安装

```bash
git clone https://github.com/sissima95-pixel/PriceLens.git && cd PriceLens && pip install -e .
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
pricelens --markets US --input data.xlsx --title "US Personal Fans" --subtitle "2026.5.1 – 7.31" --output ./report --yes
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

---

## 输出报告

每次运行生成两个带时间戳的文件:

- `asin_detail_YYYYMMDD_HHMMSS.xlsx` — 格式化 Excel 明细(Segoe UI 字体、Indigo 表头、交替行色、冻结首行)
- `竞品ASIN分析报告_YYYYMMDD_HHMMSS.html` — 可交互报告

### HTML 报告包含

1. **Hero Header** — Indigo→Violet→Pink 渐变,标题居中
2. **Price Tier Cards** — 3 张卡片(Entry/Mid-tier/Premium),显示数量、占比、均价,**可点击过滤 Volume 图**
3. **ASIN Count 柱形图** — 竖向柱形图,绿/蓝/粉三色,**可点击过滤 Volume 图**
4. **Brand Avg Price** — 横向条形图 Top 12,**可点击过滤 Volume 图**
5. **Brand Bubble Cloud** — 彩色气泡 Top 20,**可点击过滤 Volume 图**
6. **Search Volume by ASIN (Top 15)** — 动态横向柱状图,根据价格段/品牌点击实时过滤
7. **明细表** — 每列支持排序 ↕ + 筛选 ▼(数值范围 / 文本多选 + Select All)

### 交互功能

- 点击价格段卡片/柱条 → Volume 图显示该段内 ASIN
- 点击品牌气泡/条形 → Volume 图显示该品牌 ASIN
- 再次点击取消筛选,恢复全部 Top 15

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
  --title          报告标题
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
| 100–300 | 15–40 分钟 | Amazon 限流 |
| > 300 | 较长 | 用 `--delay 1.0 --workers 3` |

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
输出: HTML 报告 + Excel
```

**核心洞察**: Amazon 按 delivery address(而非 IP)决定展示什么价格。通过 cookie 注入本地邮编 + 币种,无论用户在哪里,都能拿到目标市场的本地原生价格。

---

## 品牌识别逻辑 (v1.2.2 — Byline-First)

优先级顺序:
1. **Byline anchor** — "Visit the X Store"(最准确)
2. **Store URL** — /stores/BRAND/page/
3. **Store URL old** — /BRAND/b/ref=
4. **Product detail table** — Brand: X
5. **JSON payload** — "brand":"X"
6. **Title 首词** — 最后兜底(仅在以上全无时使用)

之前的 title-first 策略在 Personal Fan 等品类会把描述词(Portable/Wireless)误认为品牌,已修复。

---

## 价格分档

- 固定 3 档:Entry / Mid-tier / Premium
- 等宽分割:按整个类目 (max-min)/3 分档,每档覆盖相同价格跨度
- 不再使用分位数(避免低端过细、高端过粗)

---

## 设计系统

- **色板**: Indigo/Violet 主色 (#6366f1),10 色图表循环
- **字体**: Inter (Google Fonts) + SF Mono 等宽
- **Hero**: 紫色渐变 + 径向装饰光晕
- **卡片**: 14px 圆角,轻阴影,hover 上浮
- **背景**: #FAFAFA

---

## 与 AI Agent 集成

| Agent | 集成方式 |
|-------|---------|
| Orcha | Shell tool 调用,skill 文件在 `skills/orcha/` |
| Claude Code | Bash tool 调用,skill 文件在 `skills/claude-code/` |
| Kiro / Cursor | Terminal 命令调用 |
| 人工 | 直接在终端运行 |

---

## 合规提醒

- ⚠️ **仅限 AST 内部使用**
- 不包含任何内部 API 调用,全部基于公开前端页面
- 分享给客户前需去除内部标注,使用 Peer Benchmarking 匿名化框架

---

## 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| 1.2.2 | 2026-08-11 | 品牌识别改为 byline-first;新设计系统(Indigo 色板、Inter 字体、Hero 渐变);HTML 柱形图(不再用模糊 canvas);品牌气泡云;交互过滤(点击价格段/品牌→Volume 图动态更新);Search Volume 改为 Top 15;去除 x 轴数字 |
| 1.1.1 | 2026-08-07 | UI 对齐 AU RV Dashboard 风格;输出改为 Excel(.xlsx);文件名改为 `asin_detail` + `竞品ASIN分析报告`;等宽 3 档价格段;标题居中;筛选加 Select All;明细表可滚动 |
| 1.1.0 | 2026-08-05 | reporter.py 完整重写(替换损坏文件);新增 `--subtitle` 参数;HTML 骨架修复 |
| 1.0.0 | 2026-08-04 | 首版发布:17 市场支持,品牌识别,HTML 报告 + CSV |
