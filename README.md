# 投资日报 Skills

一套给 **Claude Code / CodeBuddy / Cursor** 等本地 Agent 使用的投资日报 Skill,帮你生成个性化的每日 A 股 / 美股 / 港股日报。

**两种交付物**:
- 📷 **PNG 长图**——方便手机保存、微信转发、朋友圈分享(需要本机装有 Chrome / Edge / Chromium 任一;默认开)
- 🌐 **HTML 网页**——原始可视化日报,含图表、SVG 饼图、响应式布局(始终生成)

---

## 一键安装

```bash
curl -fsSL https://github.com/Lost-in-mundane/cxt-invest-DailyReport/releases/latest/download/install.sh | bash
```

脚本会自动:
- 下载最新版本的安装包
- 探测本机的 `~/.claude/skills/` / `~/.codebuddy/skills/` / `~/.cursor/skills/` 并挨个安装
- 创建画像目录 `~/.daily-report/`
- 检查 Python 依赖(akshare / yfinance)并给出提示

### 安装指定版本

```bash
curl -fsSL https://github.com/Lost-in-mundane/cxt-invest-DailyReport/releases/latest/download/install.sh | bash -s -- --version v0.1.0
```

### 指定安装目录

```bash
curl -fsSL https://.../install.sh | bash -s -- --dir /custom/skills/path
```

---

## 更新

**就是重新跑一次安装命令**:

```bash
curl -fsSL https://github.com/Lost-in-mundane/cxt-invest-DailyReport/releases/latest/download/install.sh | bash
```

脚本会自动检测已安装的位置、备份旧版本(加 `.bak.{timestamp}` 后缀)、覆盖成新版。

---

## 卸载

安装后本机留了一份 uninstall 脚本,两种方式任选:

```bash
# 方式 1: 跑本地 uninstall 脚本(推荐,快)
bash ~/.claude/skills/.daily-report-skills-manifest/uninstall.sh --uninstall

# 方式 2: 再 curl 一次
curl -fsSL https://github.com/Lost-in-mundane/cxt-invest-DailyReport/releases/latest/download/install.sh | bash -s -- --uninstall
```

**卸载行为**:
- 删除三个 skill 目录(所有安装到的位置)
- 删除 manifest 和 uninstall.sh 自己
- **保留** `~/.daily-report/`(里面有你的画像和历史日报,需手动删)

### 查看装在哪里

```bash
bash ~/.claude/skills/.daily-report-skills-manifest/uninstall.sh --list
```

---

## 包含的 Skills

| Skill | 作用 | 触发示例 |
|---|---|---|
| `daily-report` | 生成当天日报(L1 通用 / L2 自选 / L3 持仓 三档自适应) | "日报"、"今天行情怎么样"、"盘后总结" |
| `daily-report-setup` | 对话式配置个人画像(关注市场、自选、持仓、偏好) | "设置日报"、"加一只茅台"、"告诉你我的持仓" |
| `daily-report-reset` | 清空或部分重置画像数据 | "清空日报"、"只清持仓"、"重置画像" |

画像数据统一存在 `~/.daily-report/profile.json`,三个 skill 共享;生成的日报 HTML/PNG 也落在同一目录。

---

## 首次使用

安装完成后,**重启 Agent**(Claude Code / CodeBuddy)再新开会话。直接跟 Agent 说话:

**首次配置画像**:
> "设置日报"

按提示告诉它你关注哪些市场、自选哪些股票、持仓多少。也可以直接发持仓截图(支持视觉的模型能识别)。

**生成日报**:
> "日报" / "今天行情怎么样" / "盘后总结"

Agent 会把日报保存到 `~/.daily-report/`,并在聊天里 inline 预览 PNG。

**修改画像**:
> "加一只腾讯" / "更新持仓" / "换成详细一点的风格"

**清空画像**:
> "清空日报" / "只清持仓"

---

## 建议的外部依赖(软依赖)

```bash
pip install akshare yfinance
```

两个库都是**软依赖**——不装也能跑(会自动降级到 WebSearch),但装上日报耗时从分钟级降到 10 秒级。

**按市场分工**:

| 标的类型 | 首选 | 次选 | 兜底 |
|---|---|---|---|
| A 股 / A 股指数 / A 股 ETF | **akshare** | yfinance(`.SS`/`.SZ` 后缀) | WebSearch |
| 港股 | yfinance(`.HK` 后缀) | akshare | WebSearch |
| 美股 / 美股指数 | yfinance | — | WebSearch |

**PNG 生成依赖 Chrome/Chromium/Edge**——macOS 和多数 Linux 桌面已默认有。

---

## 性能参考(本机实测)

| 场景 | 耗时 |
|---|---|
| 完整 L3 日报(含 5 只持仓 + 并发 WebSearch + PNG) | 20-35s |
| 行情数据拉取(indices + quotes + sectors 并发) | 3-7s |
| PNG 截图(探测高度 + 2x retina) | 5-7s |

---

## 数据与隐私

- 所有画像、日报数据都存在**你自己的电脑**上(`~/.daily-report/`)
- Skill 不会把数据上传到任何第三方服务
- 联网的部分只有:akshare(东方财富 / 新浪财经公开接口)、yfinance(Yahoo Finance 公开行情)、WebSearch(通过 Agent 自带的抓取工具)

如果你想多端同步画像,把 `~/.daily-report/` 纳入 dotfiles / iCloud / Dropbox 即可。

---

## 目录结构

```
cxt-invest-DailyReport/
├── README.md                         ← 你正在读的文档
├── install.sh                        ← 一键安装 / 更新 / 卸载脚本
├── .github/workflows/release.yml     ← push tag 自动打包发布
├── _shared/                          ← 共享脚本源码
│   ├── fetch.py                      ← 行情数据获取(install.sh 分发)
│   └── render.py                     ← HTML 渲染器(同上)
├── daily-report/
│   ├── SKILL.md                      ← 完整的 skill 指令书
│   ├── references/
│   │   └── chart_templates.md        ← 图表占位符规则(render.py 参考)
│   └── templates/
│       └── report_wrapper.html       ← 日报 HTML 外壳
├── daily-report-setup/
│   ├── SKILL.md
│   └── references/
│       └── profile_schema.md         ← profile.json 完整字段定义
└── daily-report-reset/
    └── SKILL.md
```

> 📦 **设计说明**:`_shared/` 下的 `fetch.py` 和 `render.py` 是唯一源码,`install.sh` 会在安装时把它们分发到需要的 skill 的 `scripts/` 下(daily-report 拿 fetch+render,daily-report-setup 只拿 fetch)。每个 skill 装到 `~/.claude/skills/<name>/` 后都是自包含的。

---

## 本地开发

仓库克隆下来就可以本地跑 install.sh,会自动走"本地模式"(不下载,直接用当前目录):

```bash
git clone https://github.com/Lost-in-mundane/cxt-invest-DailyReport.git
cd cxt-invest-DailyReport
bash install.sh --dir /tmp/test-install
```

改完代码测试完,打 tag 触发发布:

```bash
git tag v0.1.1
git push origin v0.1.1
# → GitHub Actions 自动:
#   1. 打 daily-report-skills.zip
#   2. 注入版本号到 install.sh
#   3. 创建 Release 并上传 install.sh + zip
```

---

## 已知限制

- 日报里的"投资建议"类措辞会被刻意规避——本 skill 不做投资建议,只做信息组织和翻译
- 市场休市日(周末、节假日)数据会回落到昨收
- 截图识别持仓依赖模型的视觉能力,没视觉能力的模型会提示用文字输入
- yfinance 对 A 股的 symbol 格式要求严格(沪市 `.SS`、深市 `.SZ`),输入时注意;akshare 对 A 股 symbol 更宽容(纯 6 位代码即可)

---

## 许可

MIT
