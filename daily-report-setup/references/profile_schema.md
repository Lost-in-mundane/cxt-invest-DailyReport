# Profile Schema

`profile.json` 是三个 daily-report skill 共享的用户投资画像文件。

## 存储位置

```
~/.daily-report/profile.json
```

位于本机用户家目录下,**跨 thread、跨项目全局共享**。用户在任何路径下启动 Agent 都读取同一份画像。

> 提示:多端同步 profile 可以把 `~/.daily-report/` 纳入 dotfiles / iCloud / dropbox 等同步方案,本 skill 本身不做云端同步。

## 完整 Schema

```json
{
  "version": 1,
  "created_at": "2026-04-21T10:00:00+08:00",
  "updated_at": "2026-04-21T10:00:00+08:00",
  "L2": {
    "markets": ["A股", "美股", "港股"],
    "watchlist": [
      {
        "name": "贵州茅台",
        "symbol": "600519.SS",
        "type": "stock",
        "sector": "白酒"
      }
    ]
  },
  "L3": {
    "positions": [
      {
        "name": "贵州茅台",
        "symbol": "600519.SS",
        "amount": 52000,
        "shares": 30,
        "cost_basis": null
      }
    ]
  },
  "preferences": {
    "style": "简洁直接",
    "focus": "更关注风险提示",
    "length": "short"
  }
}
```

## 字段详解

### 顶层

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `version` | int | ✅ | schema 版本号,当前固定为 1 |
| `created_at` | string | ✅ | ISO 8601,首次创建时间 |
| `updated_at` | string | ✅ | ISO 8601,每次写入刷新 |
| `L2` | object | ✅ | 自选相关信息 |
| `L3` | object | ✅ | 持仓相关信息 |
| `preferences` | object | ✅ | 阅读偏好 |

### L2.markets

用户关注的市场范围,决定日报拉哪些指数。

- 类型:`string[]`
- 合法值:`"A股"` / `"美股"` / `"港股"` / `"日股"` / `"欧股"`
- 空数组表示未设置 → 日报默认只拉 A 股指数

### L2.watchlist[]

用户关注的自选标的。

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | string | ✅ | 中文名,用户看到的显示名称(例:"贵州茅台") |
| `symbol` | string \| null | ✅ | yfinance 代码;sector 类型可为 null |
| `type` | `"stock"` / `"fund"` / `"sector"` | ✅ | 类别 |
| `sector` | string \| null | ❌ | 所属板块,用于归因叙述(例:"白酒") |

**symbol 格式约定**(yfinance):
- 沪市 A 股:`XXXXXX.SS`(如 `600519.SS`)
- 深市 A 股:`XXXXXX.SZ`(如 `000858.SZ`)
- 港股:`XXXX.HK`(如 `0700.HK`)
- 美股:原代码(如 `NVDA`、`AAPL`)
- sector 类型:可为 null(没有对应的 ticker)

### L3.positions[]

用户实际持仓。所有条目的 symbol 建议也同时存在于 L2.watchlist 中(方便归因)。

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | string | ✅ | 中文名 |
| `symbol` | string | ✅ | yfinance 代码(不允许 null) |
| `amount` | number | ✅ | 当前市值,单位人民币元 |
| `shares` | number \| null | ❌ | 持有股数/份额 |
| `cost_basis` | number \| null | ❌ | 成本价,为 null 时日报不计算累计盈亏 |

### preferences

| 字段 | 类型 | 合法值 | 说明 |
|------|------|--------|------|
| `style` | string \| null | 自由文本 | 写作风格偏好(例:"简洁直接"/"详细丰富") |
| `focus` | string \| null | 自由文本 | 重点偏好(例:"更关注风险"/"更关注机会") |
| `length` | string \| null | `"short"` / `"medium"` / `"long"` / null | 日报长度档位 |

---

## Level 推断规则

日报读取 profile 后按以下规则自动判级(**不在 profile 里存 level 字段**):

```
if L3.positions 非空 → L3
elif L2.watchlist 非空 → L2
else → L1
```

**容错**:文件不存在、JSON 解析失败、字段缺失 → 一律降级为 L1,不报错。

---

## 空状态(L1 冷启动)

```json
{
  "version": 1,
  "created_at": "2026-04-21T10:00:00+08:00",
  "updated_at": "2026-04-21T10:00:00+08:00",
  "L2": { "markets": [], "watchlist": [] },
  "L3": { "positions": [] },
  "preferences": { "style": null, "focus": null, "length": null }
}
```

---

## 合并策略

setup / reset 写入时遵循**合并更新**原则:

1. 读现有 profile(不存在则用上面的空状态)
2. 只覆盖用户本轮明确提到的字段
3. 未提及的字段**保持原值**
4. 刷新 `updated_at`
5. write_file 覆写整个文件

**示例**:用户说"我再加一只腾讯",操作应为:
- 读出现有 watchlist
- 追加新条目 `{"name": "腾讯控股", "symbol": "0700.HK", ...}`
- 其他字段(markets、preferences、positions)全部保留
- 写回

---

## reset 粒度

| 粒度 | 操作 |
|------|------|
| 全清 | 写入空状态(保留 schema 结构,不删文件) |
| 只清持仓 | `L3.positions = []`,其他保留 |
| 只清自选 | `L2.watchlist = []` **且** `L3.positions = []`(持仓依赖自选,必须联动清空) |
| 只清偏好 | `preferences.* = null`,L2/L3 保留 |
