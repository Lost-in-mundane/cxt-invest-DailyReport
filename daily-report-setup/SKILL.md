---
name: daily-report-setup
description: 配置或更新投资日报的个人画像,采用对话式引导逐步收集用户关注的市场、自选标的、持仓金额、阅读偏好。当用户说"设置日报"、"配置日报"、"添加自选"、"更新持仓"、"我想关注某只股票"、"告诉你我的持仓"、"设置投资画像"、"加一只XX"时触发。生成 profile.json 供 daily-report 读取;支持持仓截图视觉识别(无需 OCR)。
---

# 日报画像设置

通过对话渐进式收集用户的投资画像,写入 `~/.daily-report/profile.json`,供 daily-report skill 生成个性化日报。

## 路径约定

- 画像文件:`~/.daily-report/profile.json`(本机文件系统,不是沙箱挂载点)
- 首次运行若目录不存在,先 `mkdir -p ~/.daily-report`
- 读写统一使用 Agent 提供的本地文件工具(Read / Write / Bash);若工具不支持 `~`,改用 `$HOME/.daily-report/profile.json` 或绝对路径

## Overview

**不要给用户填表**。用自然对话一轮一个问题推进,每一步都可以跳过。用户说"没了"/"就这些"就可以结束。

完整的 profile 字段定义在本 skill 目录下的 `references/profile_schema.md`,执行前务必先 Read 它,了解字段约束(特别是 symbol 格式和 type 枚举)。

## 执行流

### Step 1:读 schema + 读现有 profile

先 Read `references/profile_schema.md`(相对本 SKILL.md 所在目录),记住字段结构和 symbol 格式约定。

然后 Read `~/.daily-report/profile.json`:
- 读取成功 → 记住现有字段,进入 Step 2
- 文件不存在或 JSON 解析失败 → 视作全新 profile,直接进入 Step 3

### Step 2:展示现状并询问

对已存在的 profile,用一句话摘要当前状态,问用户改什么。不要直接展示 JSON,用自然语言:

> "你当前关注 A 股、美股,自选 3 只(茅台、英伟达、芯片 ETF),暂无持仓。要改哪部分?可以说'加一只 XX'、'更新持仓'、'换个风格偏好',或者'重新设置'。"

根据用户回答跳到对应的采集步骤。

### Step 3:渐进式采集

**一次只问一个问题**,按以下顺序推进。用户明确跳过或说"就这些"就结束。

#### 3.1 关注市场(markets)

问:「你平时主要关注哪些市场?A 股、美股、港股都可以。」

用户回答 → 写入 `L2.markets`(合法值见 schema)

#### 3.2 自选标的(watchlist)

问:「有没有重点关注的股票、基金或板块?说名字就行,也可以批量说,比如'茅台、英伟达、芯片 ETF'。」

**采集规则**:
- **验证 symbol 用本 skill 的 fetch.py 脚本**(相对 SKILL.md 路径 `scripts/fetch.py`,不要手写 python3 -c):
  ```bash
  # A 股:按中文名搜(2 秒出结果)
  python3 scripts/fetch.py search --keyword 茅台
  # → {"results":[{"code":"600519","name":"贵州茅台","yfinance_symbol":"600519.SS"}]}

  # 跨市场验证某个 symbol 真的能拿到行情
  python3 scripts/fetch.py quotes --symbols 600519.SS,NVDA,0700.HK
  # 某只返回 {"status":"unavailable"} 说明 symbol 错了
  ```
  > Claude Code 里 Bash 工具在 skill 目录下运行;若 cwd 不在,可用绝对路径
  > `python3 "$(dirname "$(find ~/.claude/skills ~/.codebuddy/skills -name 'fetch.py' -path '*daily-report-setup*' 2>/dev/null | head -1)")/fetch.py"` 自发现。

- **工具调用预算**:每只标的的 symbol 验证**最多 2 次本地调用 + 1 次 WebSearch**。走完还拿不到就告知用户"没查到 {名字},换个说法?",不要反复重试。

- 用户说"茅台" 直接当"贵州茅台 600519.SS"处理,**不要反问"请问是贵州茅台吗"**
- 用户说"XX 板块" → `type = "sector"`,`symbol = null`,不用验证
- 美股 / 港股 symbol 推断:美股用原代码(NVDA、AAPL);港股 4 位+`.HK`(0700.HK)
- 支持批量:用户一次说多个标的 → `fetch.py quotes --symbols` 一次传多个,**一条命令验证全部**,不要逐只调

每个条目填全 4 个字段:`name`, `symbol`, `type`, `sector`(type 参考:个股→stock、基金/ETF→fund、板块→sector)。

#### 3.3 持仓(positions)

问:「有没有实际持仓想跟踪?可以告诉我标的和大概金额,'茅台 5 万、英伟达 2 万'这样说就行。也可以直接发持仓截图,我来识别。」

**两种输入方式**:

**A. 文字输入** → 解析「名字 + 金额」对,写入 `L3.positions`。金额单位默认为元(5 万 = 50000)。

**B. 截图输入** → 用户发图后,你直接看图识别(多数现代 Agent 都有视觉能力)。若当前模型无视觉能力,友好地告知用户"请用文字给我持仓"。从截图里提取:
- 标的名
- 持有市值 / 金额
- 份额或股数(如果图上有)
- 成本价(如果图上有,否则 null)

**提取后向用户确认一次**再写入:
> "从截图识别到:贵州茅台 52000 元 / 30 股、招商白酒 28000 元 / 15000 份。金额单位都是元,对吗?"

用户确认后写入 `L3.positions`。

**symbol 处理**:如果持仓的 name 已在 `L2.watchlist` 里,symbol 直接复用;否则按 3.2 的规则验证 symbol。

持仓的标的通常也应该在 watchlist 里。如果用户说的持仓不在自选里,**主动加到 watchlist**(不用再问),这样日报能自然覆盖。

#### 3.4 阅读偏好(preferences)

问:「对日报风格有没有偏好?简洁一点还是详细一点?更关注风险还是机会?」

可以不问,默认值即可(全 null)。

- `style`:自由文本
- `focus`:自由文本
- `length`:`"short"` / `"medium"` / `"long"` / null

### Step 4:合并 + 写入

**关键:合并式更新,不要覆盖未提及的字段**。

1. 再次 Read `~/.daily-report/profile.json` 拿当前文件内容(可能为空)
2. 在原 profile 基础上合并本轮收集到的字段
3. 刷新 `updated_at` 为当前 ISO 时间(Bash `date -Iseconds`)
4. 如果是首次创建,同时设置 `created_at`
5. 先 `mkdir -p ~/.daily-report`,再 Write `~/.daily-report/profile.json` 覆写完整 JSON

> ⚠️ **一次性写完**:不要多次 str_replace。在内存里拼装好完整 JSON 再一次 Write。

### Step 5:确认

展示更新后的画像摘要(**不展示 JSON**),用自然语言:

> "已更新:关注 A 股 / 美股,自选 3 只(茅台 / 英伟达 / 芯片 ETF),持仓 3 只共 ¥98,000,偏好简洁直接。说'日报'即可生成。"

末尾提示:「如果之后还要调整,随时说就行。」

## 行为规则

### 渐进式
- **一次问一个问题**,不要一次性问完所有字段
- 用户可随时"跳过"/"就这些"/"先这样"结束

### 能推断就不问
- 用户说"加一只茅台" → 直接加,不问"请问是贵州茅台吗"
- 用户说"5 万持仓" → 直接按 50000 元处理,不问"是人民币吗"

### 批量支持
- 用户一次说多个自选 → 全部采集完再统一写入,不要一个一个问

### symbol 验证
- 写入 watchlist / positions 前,用 `fetch.py search`(查代码)或 `fetch.py quotes`(验证行情可达)二选一确认 symbol 有效
- 验证失败最多再试 1 次(换关键词或换 symbol 格式);**不要连续重试 3 次以上**
- 最终失败 → 告知用户"没查到 {名字} 的行情数据,确认一下名字对吗?"

### 合并不覆盖
- 每次写入前必须先 Read 原文件
- 只改用户本轮明确提到的字段
- 没提到的字段**保持原值**

### 截图处理
- 用户发持仓截图 → 直接看图识别,不要说"我不能处理图片"
- 识别后必须先向用户确认再写入

### 不引导跳转
- 结束语只说"说'日报'即可生成",不要引导去别的页面/功能

## 异常处理

| 场景 | 处理 |
|------|------|
| profile.json 存在但 JSON 非法 | 当作全新 profile 开始采集,完成后覆写 |
| `fetch.py search` 返回 `not_found` / `unavailable` | 换 `quotes --symbols` 验证猜测的 symbol;再失败告知用户"没查到,换个说法?" |
| 用户说的名字太模糊(如"中概") | 问澄清:"是中概 ETF 还是具体某只中概股?" |
| 用户发的不是持仓截图(是其他图) | 告知"这张图看起来不是持仓截图,能发下对账单或持仓列表吗?" |
| 本机既没装 akshare 也没装 yfinance | fetch.py 会自动返回 `unavailable`;告诉用户"建议 `pip install akshare yfinance` 以便日报拉行情更稳",然后用 WebSearch 找一次代码(最多 1 次)后就停下 |
