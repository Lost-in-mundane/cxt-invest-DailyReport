# 图表模板

4 种自包含 HTML/SVG 模板,基于财小通日报 V6 demo 的视觉设计。LLM 根据数据**只做字符串替换**,不要自创样式或修改结构。

---

## 替换规则(通用)

### 占位符

| 占位符 | 替换为 |
|--------|--------|
| `{{NAME}}` | 标的名称(中文原文) |
| `{{VALUE_FMT}}` | 格式化后的数值(见下方格式化规则) |
| `{{VALUE_UNIT}}` | 数值单位:"点" / "元" / "港元" / "美元" / "" |
| `{{PCT_WITH_SIGN}}` | 涨跌幅带符号 2 位小数,如 `+0.95%` 或 `-0.35%` |
| `{{COLOR}}` | `#fa5252`(红,pct ≥ 0) 或 `#43a047`(绿,pct < 0) —— 财小通 V6 配色 |
| `{{WIDTH_PCT}}` | 条形宽度百分比,计算公式见各模板 |
| `{{AMOUNT}}` | 金额(千分位 + ¥ 前缀),如 `¥52,000` |
| `{{PNL_WITH_SIGN}}` | 盈亏金额带符号,如 `+¥392` 或 `-¥420` |

### 数值格式化规则(VALUE_FMT)

根据数值大小选择显示方式:
- `value >= 10000` → `{value/10000}w`(例:45612 → `4.56w`)
- `value >= 1000` → 千分位整数(例:4012.53 → `4,013`)
- 否则 → 保留 1 位小数(例:1.825 → `1.8`)

### 硬规则

- **禁止**在替换值里引入 `<` / `>` / `&` / `"` / `'`(会破坏 HTML)。如果标的名含这些字符,用空格替代。
- **禁止**修改模板里的 class 名和标签结构
- **禁止**在输出里留下任何 `{{...}}` 占位符
- 每次替换完成后,整段 HTML 作为一个字符串存储,后续拼装时整体插入

---

## 模板 1:market_grid(指数 2×2 数据卡片,L1+)

**用途**:展示 4 个核心指数/参考数据,单点大数字,适合第二层"市场行情分析"。这是 V6 的核心视觉设计。

### 外框模板

```html
<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:16px 0">
  {{PILLS}}
</div>
```

### 单个 Pill 模板(每项重复一次)

```html
<div style="background:#fff;border-radius:16px;padding:14px 16px 12px;border:1.5px solid rgba(0,0,0,0.05);overflow:hidden">
  <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px">
    <span style="font-size:13px;color:rgba(0,0,0,0.4);font-weight:500">{{NAME}}</span>
    <span style="font-size:15px;font-weight:700;color:{{COLOR}}">{{PCT_WITH_SIGN}}</span>
  </div>
  <div style="font-size:14px;color:rgba(0,0,0,0.55);font-weight:600">{{VALUE_FMT}}<span style="font-size:11px;color:rgba(0,0,0,0.35);font-weight:400;margin-left:4px">{{VALUE_UNIT}}</span></div>
</div>
```

### 使用步骤

1. 准备 4 项数据,每项 `{name, value, change_pct, unit}`
2. 数据顺序建议:A 股 2 个 + 海外 1 个 + 参考(原油/汇率)1 个;或者按 profile.markets 决定
3. 对每项:按 VALUE_FMT 规则格式化数值,按正负选 COLOR
4. 复制"单个 Pill 模板"4 次,替换占位符
5. 拼接所有 pill HTML,替换外框的 `{{PILLS}}`

### 示例输入

```
items = [
  {"name": "上证指数",    "value": 4012.53, "change_pct": 0.95, "unit": "点"},
  {"name": "创业板指",    "value": 3245.12, "change_pct": 1.87, "unit": "点"},
  {"name": "纳斯达克100", "value": 23847,   "change_pct": 0.62, "unit": "点"},
  {"name": "原油",        "value": 73.2,    "change_pct": -2.10, "unit": "美元"}
]
```

> 注意:**条目数量控制在 2-4 个**(2 个就是单行,4 个是 2×2)。超过 4 个会破坏 grid 美观,分两组渲染。

---

## 模板 2:watchlist_bars(自选渐变条形图,L2+)

**用途**:展示用户自选标的按涨跌幅排序的条形图,用 linear-gradient 渐变效果。V6 的"第三层·自选总览"核心视觉。

### 外框模板

```html
<div style="display:flex;flex-direction:column;gap:14px;margin:16px 0">
  {{ROWS}}
</div>
```

### 行模板(每条数据重复一次)

```html
<div style="display:flex;align-items:center;gap:12px">
  <div style="width:96px;flex-shrink:0;font-size:13px;color:rgba(0,0,0,0.55);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{{NAME}}</div>
  <div style="flex:1;height:16px;position:relative">
    <div style="height:100%;width:{{WIDTH_PCT}}%;background:linear-gradient(90deg,{{COLOR}}30,{{COLOR}}B0);border-radius:0 100px 100px 0"></div>
  </div>
  <div style="width:64px;text-align:right;flex-shrink:0;font-size:15px;font-weight:700;color:{{COLOR}}">{{PCT_WITH_SIGN}}</div>
</div>
```

### 使用步骤

1. **必须先按 change_pct 从大到小排序**(最强领涨在上,最弱领跌在下)
2. 计算 `max_abs = max(max(|change_pct_i|), 2)`(最小取 2 避免条过短)
3. 每项:`WIDTH_PCT = |change_pct| / (max_abs * 1.15) * 100`(V6 用 1.15 系数留白)
4. COLOR 根据正负选 `#fa5252` / `#43a047`
5. 注意:gradient 的两个 stop 用 `{{COLOR}}30` 和 `{{COLOR}}B0` —— hex 颜色后面跟两位是透明度。模板里直接字面拼接即可

### 示例输入

```
items = [
  {"name": "华夏芯片ETF", "change_pct": 2.18},
  {"name": "英伟达",      "change_pct": 1.06},
  {"name": "贵州茅台",    "change_pct": -0.35}
]
max_abs = max(2.18, 2) = 2.18
```

### 视觉说明

- 名字宽度 96px(可以显示 4-5 个中文字,过长 ellipsis)
- 条形只有右侧圆角(视觉上从左侧起)
- gradient 从浅到深,阅读感强

---

## 模板 3:pnl_waterfall(持仓盈亏瀑布,L3)

**用途**:展示每个持仓的盈亏金额贡献 + 合计。和 watchlist_bars 一致的渐变条形风格。

### 外框模板

```html
<div style="margin:16px 0">
  <div style="display:flex;flex-direction:column;gap:14px">
    {{ROWS}}
  </div>
  <div style="display:flex;align-items:center;gap:12px;margin-top:14px;padding-top:14px;border-top:1px dashed rgba(0,0,0,0.12)">
    <div style="width:96px;flex-shrink:0;font-size:14px;font-weight:600;color:rgba(0,0,0,0.75)">合计</div>
    <div style="flex:1"></div>
    <div style="width:80px;text-align:right;flex-shrink:0;font-size:16px;font-weight:700;color:{{TOTAL_COLOR}}">{{TOTAL_PNL_WITH_SIGN}}</div>
  </div>
</div>
```

### 行模板

```html
<div style="display:flex;align-items:center;gap:12px">
  <div style="width:96px;flex-shrink:0;font-size:13px;color:rgba(0,0,0,0.55);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{{NAME}}</div>
  <div style="flex:1;height:16px;position:relative">
    <div style="height:100%;width:{{WIDTH_PCT}}%;background:linear-gradient(90deg,{{COLOR}}30,{{COLOR}}B0);border-radius:0 100px 100px 0"></div>
  </div>
  <div style="width:80px;text-align:right;flex-shrink:0;font-size:15px;font-weight:700;color:{{COLOR}}">{{PNL_WITH_SIGN}}</div>
</div>
```

### 使用步骤

1. 每项盈亏:`pnl_i = position.amount × change_pct_i / 100`
2. `total_pnl = sum(pnl)`
3. `max_abs_pnl = max(max(|pnl_i|), 100)`(避免除零)
4. 对每项:`WIDTH_PCT = |pnl| / (max_abs_pnl * 1.15) * 100`
5. `TOTAL_COLOR` 根据 `total_pnl` 正负选色
6. `PNL_WITH_SIGN` / `TOTAL_PNL_WITH_SIGN`:`+¥392` / `-¥420`(负号用 `-`)
7. **按盈亏绝对值排序**(最大正贡献在上,最大负贡献在下)

---

## 模板 4:position_pie(仓位占比饼图,L3)

**用途**:展示每个持仓在总资产里的占比。SVG 环形图。

### 完整模板

```html
<div style="margin:16px 0;background:#fff;border-radius:16px;padding:16px;border:1.5px solid rgba(0,0,0,0.05)">
  <div style="font-size:13px;color:rgba(0,0,0,0.4);font-weight:500;margin-bottom:12px">仓位分布</div>
  <div style="display:flex;align-items:center;gap:16px">
    <svg width="110" height="110" viewBox="0 0 42 42" style="flex-shrink:0">
      <circle cx="21" cy="21" r="15.915" fill="#fff" stroke="#f3f4f6" stroke-width="6"/>
      {{ARCS}}
    </svg>
    <div style="flex:1;display:flex;flex-direction:column;gap:6px;font-size:12px">
      {{LEGEND}}
    </div>
  </div>
</div>
```

### SVG 弧段模板(每个持仓一个)

```html
<circle cx="21" cy="21" r="15.915" fill="transparent" stroke="{{COLOR}}" stroke-width="6" stroke-dasharray="{{DASH}} 100" stroke-dashoffset="{{OFFSET}}" transform="rotate(-90 21 21)"/>
```

### 图例项模板

```html
<div style="display:flex;align-items:center;gap:6px">
  <span style="width:10px;height:10px;border-radius:2px;background:{{COLOR}};flex-shrink:0"></span>
  <span style="color:rgba(0,0,0,0.55);flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{{NAME}}</span>
  <span style="color:rgba(0,0,0,0.4);flex-shrink:0;font-weight:500">{{PCT_INT}}%</span>
</div>
```

### 使用步骤

1. `total_amount = sum(position.amount)`
2. 对每个持仓:`pct = amount / total_amount * 100`(保留整数)
3. **累计 offset**:第 k 项 `DASH = pct`,`OFFSET = 100 - (sum of pct[0..k-1])`
   - 第 0 项 OFFSET = 100,第 1 项 OFFSET = 100 - pct[0],第 2 项 OFFSET = 100 - pct[0] - pct[1]...
4. **COLOR 按顺序轮播**:
   ```
   palette = ["#fa5252", "#2470EB", "#43a047", "#ff9800", "#8b5cf6", "#ec4899", "#14b8a6", "#6366f1"]
   ```
5. 每个持仓生成 1 个弧段 + 1 个图例项

**关键公式**:`r = 15.915` 让 `2πr ≈ 100`(周长恰好 100),百分比直接对应 stroke-dasharray,简化计算。

### 示例数据

```
positions = [
  {"name": "贵州茅台",   "amount": 52000},
  {"name": "招商白酒",   "amount": 28000},
  {"name": "华夏芯片ETF", "amount": 18000}
]
total = 98000
pcts = [53, 29, 18]

弧段计算:
  茅台:   DASH=53, OFFSET=100
  白酒:   DASH=29, OFFSET=47   (100-53)
  芯片:   DASH=18, OFFSET=18   (100-53-29)
```

---

## 配色规范(财小通 V6 标准)

| 用途 | 颜色 | Hex |
|------|------|-----|
| 涨(正值) | 财小通红 | `#fa5252` |
| 跌(负值) | 财小通绿 | `#43a047` |
| 品牌蓝(标签/副标题) | V6 brand | `#2470EB` |
| 警示橙(中性标签) | V6 warning | `#ff9800` |
| 文本主色 | 深黑 70% | `rgba(0,0,0,0.7)` 或 `#1f2937` |
| 文本次色 | 黑 55% | `rgba(0,0,0,0.55)` |
| 文本辅助 | 黑 40% | `rgba(0,0,0,0.4)` |
| 卡片边框 | 黑 5% | `rgba(0,0,0,0.05)` |
| 卡片阴影 | 浅 | `0 2px 12px rgba(0,0,0,0.04)` |

---

## 错误处理

| 场景 | 处理 |
|------|------|
| 数据为空数组 | 不生成图表,跳过该 `[CHART:xxx]` 占位符,只保留正文 |
| 单个数据项 | 可以渲染,不报错 |
| 所有 pct 都是 0 | 渲染出中性灰色条(`#9ca3af`),宽度全为 0 或 2% |
| 数据项超过 8 个 | 只展示前 8 个,末尾加一行"其他 N 项"(pnl 合计/仓位合计) |
