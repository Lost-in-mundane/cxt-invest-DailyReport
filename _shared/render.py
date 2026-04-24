#!/usr/bin/env python3
"""render.py — 投资日报 HTML 渲染器。

模型输出一份结构化 JSON,本脚本负责:
- 加载 `templates/report_wrapper.html` 作为外壳
- 按 `references/chart_templates.md` 的规则渲染 4 种图表(market_grid / watchlist_bars / pnl_waterfall / position_pie)
- 替换所有 {{...}} 占位符
- 格式化数值(VALUE_FMT / PCT_WITH_SIGN / AMOUNT / PNL_WITH_SIGN)
- HTML 转义
- 写入 ~/.daily-report/daily_report_{YYYYMMDD}_{HHMM}.html

用法:
    python3 render.py --stdin < payload.json
    python3 render.py --json payload.json
    # 也支持 --out 自定义输出路径

JSON schema 见 SKILL.md。缺失字段按"省略该段落"处理,不抛异常。
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

# ---------- 配色 ----------
COLOR_UP = "#fa5252"
COLOR_DOWN = "#43a047"
COLOR_FLAT = "#9ca3af"
PIE_PALETTE = ["#fa5252", "#2470EB", "#43a047", "#ff9800", "#8b5cf6", "#ec4899", "#14b8a6", "#6366f1"]


# ---------- 格式化工具 ----------

def h(s: Any) -> str:
    """HTML 转义,并处理 None。"""
    if s is None:
        return ""
    return html.escape(str(s), quote=True)


def color_for(pct: float | None) -> str:
    if pct is None:
        return COLOR_FLAT
    if pct > 0:
        return COLOR_UP
    if pct < 0:
        return COLOR_DOWN
    return COLOR_FLAT


def fmt_value(value: float | int | None) -> str:
    if value is None:
        return "—"
    v = float(value)
    if abs(v) >= 10000:
        return f"{v/10000:.2f}w"
    if abs(v) >= 1000:
        return f"{round(v):,}"
    return f"{v:.1f}"


def fmt_pct(pct: float | None) -> str:
    if pct is None:
        return "—"
    return f"{pct:+.2f}%"


def fmt_amount(amount: float | int | None) -> str:
    if amount is None:
        return "—"
    return f"¥{round(float(amount)):,}"


def fmt_pnl(pnl: float | int | None) -> str:
    if pnl is None:
        return "—"
    v = float(pnl)
    sign = "+" if v >= 0 else "-"
    return f"{sign}¥{round(abs(v)):,}"


# ---------- 图表渲染 ----------

def render_market_grid(items: list[dict]) -> str:
    """market_grid:2x2 数据卡。"""
    if not items:
        return ""
    pills = []
    for it in items[:4]:
        name = h(it.get("name", ""))
        value = fmt_value(it.get("value"))
        unit = h(it.get("unit", ""))
        pct = it.get("change_pct")
        color = color_for(pct)
        pct_text = fmt_pct(pct)
        pills.append(
            f'<div style="background:#fff;border-radius:16px;padding:14px 16px 12px;border:1.5px solid rgba(0,0,0,0.05);overflow:hidden">'
            f'<div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px">'
            f'<span style="font-size:13px;color:rgba(0,0,0,0.4);font-weight:500">{name}</span>'
            f'<span style="font-size:15px;font-weight:700;color:{color}">{pct_text}</span>'
            f'</div>'
            f'<div style="font-size:14px;color:rgba(0,0,0,0.55);font-weight:600">{value}'
            f'<span style="font-size:11px;color:rgba(0,0,0,0.35);font-weight:400;margin-left:4px">{unit}</span>'
            f'</div></div>'
        )
    return (
        '<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:16px 0">'
        + "".join(pills)
        + "</div>"
    )


def render_watchlist_bars(items: list[dict]) -> str:
    """watchlist_bars:按 change_pct 降序的渐变条形。"""
    if not items:
        return ""
    rows_data = sorted(
        [it for it in items if it.get("change_pct") is not None],
        key=lambda x: x["change_pct"],
        reverse=True,
    )
    if not rows_data:
        return ""
    max_abs = max(max(abs(it["change_pct"]) for it in rows_data), 2.0)
    rows = []
    for it in rows_data:
        name = h(it.get("name", ""))
        pct = it["change_pct"]
        color = color_for(pct)
        width = abs(pct) / (max_abs * 1.15) * 100
        rows.append(
            f'<div style="display:flex;align-items:center;gap:12px">'
            f'<div style="width:96px;flex-shrink:0;font-size:13px;color:rgba(0,0,0,0.55);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{name}</div>'
            f'<div style="flex:1;height:16px;position:relative">'
            f'<div style="height:100%;width:{width:.1f}%;background:linear-gradient(90deg,{color}30,{color}B0);border-radius:0 100px 100px 0"></div>'
            f'</div>'
            f'<div style="width:64px;text-align:right;flex-shrink:0;font-size:15px;font-weight:700;color:{color}">{fmt_pct(pct)}</div>'
            f'</div>'
        )
    return (
        '<div style="display:flex;flex-direction:column;gap:14px;margin:16px 0">'
        + "".join(rows)
        + "</div>"
    )


def render_pnl_waterfall(items: list[dict]) -> str:
    """pnl_waterfall:按 |pnl| 降序,底部合计。"""
    if not items:
        return ""
    rows_data = sorted(
        [it for it in items if it.get("pnl") is not None],
        key=lambda x: abs(x["pnl"]),
        reverse=True,
    )
    if not rows_data:
        return ""
    max_abs = max(max(abs(it["pnl"]) for it in rows_data), 100.0)
    total_pnl = sum(it["pnl"] for it in rows_data)
    total_color = color_for(total_pnl if total_pnl != 0 else None)
    rows = []
    for it in rows_data:
        name = h(it.get("name", ""))
        pnl = it["pnl"]
        color = color_for(pnl)
        width = abs(pnl) / (max_abs * 1.15) * 100
        rows.append(
            f'<div style="display:flex;align-items:center;gap:12px">'
            f'<div style="width:96px;flex-shrink:0;font-size:13px;color:rgba(0,0,0,0.55);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{name}</div>'
            f'<div style="flex:1;height:16px;position:relative">'
            f'<div style="height:100%;width:{width:.1f}%;background:linear-gradient(90deg,{color}30,{color}B0);border-radius:0 100px 100px 0"></div>'
            f'</div>'
            f'<div style="width:80px;text-align:right;flex-shrink:0;font-size:15px;font-weight:700;color:{color}">{fmt_pnl(pnl)}</div>'
            f'</div>'
        )
    return (
        '<div style="margin:16px 0">'
        '<div style="display:flex;flex-direction:column;gap:14px">'
        + "".join(rows) +
        '</div>'
        '<div style="display:flex;align-items:center;gap:12px;margin-top:14px;padding-top:14px;border-top:1px dashed rgba(0,0,0,0.12)">'
        '<div style="width:96px;flex-shrink:0;font-size:14px;font-weight:600;color:rgba(0,0,0,0.75)">合计</div>'
        '<div style="flex:1"></div>'
        f'<div style="width:80px;text-align:right;flex-shrink:0;font-size:16px;font-weight:700;color:{total_color}">{fmt_pnl(total_pnl)}</div>'
        '</div></div>'
    )


def render_position_pie(items: list[dict]) -> str:
    """position_pie:SVG 环形图 + 图例。"""
    if not items:
        return ""
    data = [it for it in items if it.get("amount")]
    if not data:
        return ""
    total = sum(it["amount"] for it in data)
    if total <= 0:
        return ""
    # 超过 8 个合并成"其他"
    if len(data) > 8:
        top = data[:7]
        other_amount = sum(it["amount"] for it in data[7:])
        data = top + [{"name": f"其他 {len(data)-7} 项", "amount": other_amount}]
    arcs = []
    legends = []
    cum = 0.0
    for i, it in enumerate(data):
        pct = it["amount"] / total * 100
        color = PIE_PALETTE[i % len(PIE_PALETTE)]
        dash = pct
        offset = 100 - cum
        arcs.append(
            f'<circle cx="21" cy="21" r="15.915" fill="transparent" stroke="{color}" stroke-width="6" '
            f'stroke-dasharray="{dash:.2f} 100" stroke-dashoffset="{offset:.2f}" transform="rotate(-90 21 21)"/>'
        )
        legends.append(
            f'<div style="display:flex;align-items:center;gap:6px">'
            f'<span style="width:10px;height:10px;border-radius:2px;background:{color};flex-shrink:0"></span>'
            f'<span style="color:rgba(0,0,0,0.55);flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{h(it.get("name",""))}</span>'
            f'<span style="color:rgba(0,0,0,0.4);flex-shrink:0;font-weight:500">{round(pct)}%</span>'
            f'</div>'
        )
        cum += pct
    return (
        '<div style="margin:16px 0;background:#fff;border-radius:16px;padding:16px;border:1.5px solid rgba(0,0,0,0.05)">'
        '<div style="font-size:13px;color:rgba(0,0,0,0.4);font-weight:500;margin-bottom:12px">仓位分布</div>'
        '<div style="display:flex;align-items:center;gap:16px">'
        '<svg width="110" height="110" viewBox="0 0 42 42" style="flex-shrink:0">'
        '<circle cx="21" cy="21" r="15.915" fill="#fff" stroke="#f3f4f6" stroke-width="6"/>'
        + "".join(arcs) +
        '</svg>'
        '<div style="flex:1;display:flex;flex-direction:column;gap:6px;font-size:12px">'
        + "".join(legends) +
        '</div></div></div>'
    )


# ---------- 段落 / 卡片渲染 ----------

def render_causes(causes: list[dict]) -> str:
    """market section 的因果链列表。"""
    if not causes:
        return ""
    tag_color = {
        "primary": ("rgba(36,112,235,0.12)", "#2470EB"),
        "critical": ("rgba(250,82,82,0.12)", "#fa5252"),
        "neutral": ("rgba(107,114,128,0.12)", "#6b7280"),
    }
    items = []
    for c in causes:
        tag = c.get("tag", "neutral")
        bg, fg = tag_color.get(tag, tag_color["neutral"])
        label = h(c.get("label", tag))
        text = h(c.get("text", ""))
        items.append(
            f'<div class="cause-item">'
            f'<span class="cause-tag" style="background:{bg};color:{fg}">{label}</span>'
            f'<span class="cause-text">{text}</span>'
            f'</div>'
        )
    return '<div class="cause-list">' + "".join(items) + "</div>"


def render_stock_block(idx: int, block: dict) -> str:
    """单只股票分析卡。"""
    name = h(block.get("name", ""))
    body = h(block.get("body", ""))
    pct = block.get("change_pct")
    pnl = block.get("pnl")
    pct_html = ""
    if pct is not None:
        pct_html = f'<span class="stock-pct" style="color:{color_for(pct)}">{fmt_pct(pct)}</span>'
    pnl_html = ""
    if pnl is not None:
        pnl_html = f'<span class="stock-pnl" style="color:{color_for(pnl)}">{fmt_pnl(pnl)}</span>'
    return (
        '<div class="stock-block">'
        '<div class="stock-head">'
        f'<div class="stock-idx">{idx}</div>'
        f'<div class="stock-name">{name}</div>'
        f'{pct_html}{pnl_html}'
        '</div>'
        f'<div class="stock-body">{body}</div>'
        '</div>'
    )


def render_watchlist_or_position(section: dict | None) -> str:
    """组装 L2/L3 的 section-card + 逐只 stock-block。L1 返回空。"""
    if not section:
        return ""
    level = section.get("level", "L2")
    intro = h(section.get("intro", ""))
    blocks = section.get("stock_blocks", [])

    # 图表区
    chart_html = ""
    if level == "L2":
        chart_html = render_watchlist_bars(section.get("bars") or [])
    else:  # L3
        charts = section.get("charts") or {}
        wf = render_pnl_waterfall(charts.get("pnl_waterfall") or [])
        pie = render_position_pie(charts.get("position_pie") or [])
        if wf and pie:
            chart_html = f'<div class="charts-row">{wf}{pie}</div>'
        else:
            chart_html = wf + pie

    # 股票块
    blocks_html = "".join(render_stock_block(i + 1, b) for i, b in enumerate(blocks))

    title = "我的自选" if level == "L2" else "我的持仓"
    intro_html = f'<div class="connect-text">{intro}</div>' if intro else ""

    return (
        '<section class="section-card">'
        '<div class="section-head">'
        '<span class="section-bar"></span>'
        f'<span class="section-title">{title}</span>'
        '</div>'
        f'{intro_html}{chart_html}'
        f'</section>'
        f'{blocks_html}'
    )


def render_hot_news(items: list[dict]) -> str:
    """热门新闻段(放在市场段和自选段之间)。

    每条 {title, body, sources, tag} — tag ∈ macro/sector/company/global,缺省 macro。
    空列表 → 返回空串,整个 section 不渲染。
    """
    if not items:
        return ""
    valid_tags = {"macro", "sector", "company", "global"}
    tag_labels = {"macro": "宏观", "sector": "行业", "company": "公司", "global": "海外"}
    rows = []
    for it in items:
        tag = it.get("tag") or "macro"
        if tag not in valid_tags:
            tag = "macro"
        title = h(it.get("title", ""))
        body = h(it.get("body", ""))
        sources = it.get("sources")
        sources_html = ""
        if sources:
            try:
                n = int(sources)
                if n > 0:
                    sources_html = f'<div class="news-sources">{n} 个来源</div>'
            except (TypeError, ValueError):
                pass
        rows.append(
            '<div class="news-item">'
            f'<span class="news-chip {tag}">{tag_labels[tag]}</span>'
            '<div class="news-body">'
            f'<div class="news-title">{title}</div>'
            f'<div class="news-desc">{body}</div>'
            f'{sources_html}'
            '</div></div>'
        )
    return (
        '<section class="section-card">'
        '<div class="section-head">'
        '<span class="section-bar news"></span>'
        '<span class="section-title">热门新闻</span>'
        '</div>'
        '<div class="news-list">'
        + "".join(rows) +
        '</div></section>'
    )


def render_outlook(items: list[dict]) -> str:
    """接下来关注段的 outlook-item 列表。"""
    if not items:
        return ""
    out = []
    for it in items:
        when = h(it.get("when", ""))
        title = h(it.get("title", ""))
        desc = h(it.get("desc", ""))
        when_html = f'<span class="outlook-when">{when}</span>' if when else ""
        out.append(
            '<div class="outlook-item">'
            f'{when_html}'
            '<div class="outlook-body">'
            f'<div class="outlook-title">{title}</div>'
            f'<div class="outlook-desc">{desc}</div>'
            '</div></div>'
        )
    return "".join(out)


# ---------- 主渲染 ----------

MOOD_LABEL = {"strong": "偏强", "weak": "偏弱", "mixed": "分化", "flat": "平稳"}


def find_wrapper_path(script_path: Path) -> Path:
    """找 templates/report_wrapper.html。
    脚本可能被分发到 scripts/,所以要向上找 templates/。
    """
    # 优先同级目录的 templates/(如果 render.py 被 symlink 或直接放在 skill 根)
    candidates = [
        script_path.parent.parent / "templates" / "report_wrapper.html",  # scripts/.. /templates/
        script_path.parent / "templates" / "report_wrapper.html",        # 同级
    ]
    for c in candidates:
        if c.exists():
            return c
    raise FileNotFoundError(f"找不到 report_wrapper.html;尝试过: {candidates}")


def render_html(payload: dict, wrapper_path: Path) -> str:
    """核心:把 payload 渲染成完整 HTML 字符串。"""
    wrapper = wrapper_path.read_text(encoding="utf-8")

    meta = payload.get("meta") or {}
    market = payload.get("market") or {}
    section = payload.get("watchlist_or_position")
    hot_news = payload.get("hot_news") or []
    outlook = payload.get("outlook") or []

    title = h(meta.get("title", "今日日报"))
    mood = meta.get("mood", "flat")
    mood_class = mood if mood in MOOD_LABEL else "flat"
    mood_label = MOOD_LABEL[mood_class]
    date_label = h(meta.get("date_label", ""))
    market_meta = h(meta.get("market_meta", ""))
    subtitle = meta.get("subtitle", "").strip()
    subtitle_block = f'<div class="report-sub">{h(subtitle)}</div>' if subtitle else ""

    # 市场 section = market_grid + causes
    grid_html = render_market_grid(market.get("grid") or [])
    causes_html = render_causes(market.get("causes") or [])
    market_section = grid_html + causes_html

    watchlist_or_position = render_watchlist_or_position(section)
    hot_news_section = render_hot_news(hot_news)
    outlook_items = render_outlook(outlook)

    replacements = {
        "{{TITLE}}": title,
        "{{MOOD_CLASS}}": mood_class,
        "{{MOOD_LABEL}}": mood_label,
        "{{DATE_LABEL}}": date_label,
        "{{SUBTITLE_BLOCK}}": subtitle_block,
        "{{MARKET_META}}": market_meta,
        "{{MARKET_SECTION}}": market_section,
        "{{HOT_NEWS_SECTION}}": hot_news_section,
        "{{WATCHLIST_OR_POSITION_SECTION}}": watchlist_or_position,
        "{{OUTLOOK_ITEMS}}": outlook_items,
    }
    for k, v in replacements.items():
        wrapper = wrapper.replace(k, v)

    return wrapper


def default_output_path() -> Path:
    """~/.daily-report/daily_report_YYYYMMDD_HHMM.html"""
    outdir = Path(os.path.expanduser("~/.daily-report"))
    outdir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M")
    return outdir / f"daily_report_{stamp}.html"


# ---------- PNG 截图 ----------

def find_chrome() -> str | None:
    """多级探测 Chrome 可执行路径;找不到返回 None。"""
    # macOS 常见路径
    mac_paths = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        "/Applications/Arc.app/Contents/MacOS/Arc",
    ]
    for p in mac_paths:
        if Path(p).exists():
            return p
    # Linux / WSL / PATH 兜底
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge"):
        found = shutil.which(name)
        if found:
            return found
    return None


def _probe_body_height(chrome: str, html_path: Path, width: int, timeout: int) -> int | None:
    """第一阶段:注入脚本读 scrollHeight,通过 title 回传。找不到则返回 None。"""
    probe_path = html_path.with_suffix(".probe.html")
    try:
        original = html_path.read_text(encoding="utf-8")
        probed = original.replace(
            "</body>",
            '<script>document.title="H:"+document.documentElement.scrollHeight;</script></body>',
            1,
        )
        probe_path.write_text(probed, encoding="utf-8")

        for headless_flag in ("--headless=new", "--headless"):
            cmd = [chrome, headless_flag, "--disable-gpu", "--dump-dom",
                   f"--window-size={width},800", f"file://{probe_path.absolute()}"]
            try:
                r = subprocess.run(cmd, capture_output=True, timeout=timeout, text=True)
                # 在 DOM 里找 <title>H:XXXX</title>
                import re
                m = re.search(r"<title>H:(\d+)</title>", r.stdout)
                if m:
                    return int(m.group(1))
            except subprocess.TimeoutExpired:
                continue
            except Exception:
                continue
    finally:
        try:
            probe_path.unlink()
        except Exception:
            pass
    return None


def html_to_png(
    html_path: Path,
    png_path: Path,
    width: int = 560,
    scale: int = 2,
    timeout: int = 20,
) -> tuple[bool, str]:
    """用 Chrome headless 把 HTML 截图成 PNG。

    两阶段:
      1) 用 --dump-dom + 注入脚本探测 body 真实高度(避免大片空白)
      2) 按真实高度 + padding 截图

    返回 (成功, 说明)。成功时说明是 "chrome path"; 失败时说明是错误原因,便于 skill 给用户看。
    """
    chrome = find_chrome()
    if not chrome:
        return False, "未找到 Chrome/Chromium/Edge;PNG 已跳过,HTML 仍然生成"

    # 阶段 1:探测真实高度(探测失败时用保守 fallback 高度)
    real_height = _probe_body_height(chrome, html_path, width, timeout)
    # +40 留出底部阴影空间;探测不到时给 3600 保底
    screenshot_height = (real_height + 40) if real_height else 3600

    # 阶段 2:按真实高度截图
    base_args = [
        f"--screenshot={png_path}",
        f"--window-size={width},{screenshot_height}",
        "--hide-scrollbars",
        f"--force-device-scale-factor={scale}",
        f"file://{html_path.absolute()}",
    ]

    for headless_flag in ("--headless=new", "--headless"):
        cmd = [chrome, headless_flag, "--disable-gpu"] + base_args
        try:
            subprocess.run(cmd, capture_output=True, timeout=timeout)
            if png_path.exists() and png_path.stat().st_size > 1024:
                suffix = f"{real_height}px" if real_height else "fallback 3600px"
                return True, f"{chrome} ({headless_flag}, body={suffix})"
        except subprocess.TimeoutExpired:
            return False, f"Chrome 截图超时(> {timeout}s);HTML 仍然生成"
        except Exception:
            continue

    return False, "Chrome 截图失败(两种 headless 模式都未生成有效 PNG);HTML 仍然生成"


# ---------- CLI ----------

def main() -> None:
    p = argparse.ArgumentParser(description="投资日报 HTML 渲染器")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--json", help="读 JSON 文件路径")
    g.add_argument("--stdin", action="store_true", help="从 stdin 读 JSON")
    p.add_argument("--out", help="HTML 输出路径(默认 ~/.daily-report/daily_report_*.html)")
    p.add_argument("--png", action="store_true",
                   help="同时生成 PNG 长图(需要本机装了 Chrome/Chromium/Edge;找不到会自动跳过)")
    p.add_argument("--png-width", type=int, default=560, help="PNG 宽度(默认 560,手机竖屏)")
    p.add_argument("--png-scale", type=int, default=2, help="PNG 清晰度倍率(默认 2,retina)")
    p.add_argument("--png-only", action="store_true",
                   help="生成 PNG 后删掉 HTML(默认保留 HTML);需要同时用 --png")
    args = p.parse_args()

    try:
        if args.stdin:
            payload = json.load(sys.stdin)
        else:
            with open(args.json, "r", encoding="utf-8") as f:
                payload = json.load(f)
    except Exception as e:
        print(json.dumps({"status": "error", "error": f"JSON 解析失败: {e}"}))
        sys.exit(0)

    script_path = Path(__file__).resolve()
    try:
        wrapper_path = find_wrapper_path(script_path)
    except FileNotFoundError as e:
        print(json.dumps({"status": "error", "error": str(e)}))
        sys.exit(0)

    try:
        html_out = render_html(payload, wrapper_path)
    except Exception as e:
        print(json.dumps({"status": "error", "error": f"渲染失败: {type(e).__name__}: {e}"}))
        sys.exit(0)

    out_path = Path(args.out) if args.out else default_output_path()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html_out, encoding="utf-8")

    # 未解析占位符检查
    import re
    unresolved = sorted(set(re.findall(r"\{\{[A-Z_]+\}\}", html_out)))

    result: dict[str, Any] = {
        "status": "ok",
        "html_path": str(out_path),
        "size": len(html_out),
        "unresolved_placeholders": unresolved,
    }

    # PNG 生成(可选)
    if args.png:
        png_path = out_path.with_suffix(".png")
        ok, note = html_to_png(out_path, png_path, width=args.png_width, scale=args.png_scale)
        if ok:
            result["png_path"] = str(png_path)
            result["png_size"] = png_path.stat().st_size
            if args.png_only:
                try:
                    out_path.unlink()
                    result["html_path"] = None  # 已删
                    result["note"] = "HTML 已删除(--png-only)"
                except Exception:
                    pass
        else:
            result["png_path"] = None
            result["png_error"] = note

    # 兼容字段:老代码可能期望 `path`
    result["path"] = result.get("html_path") or result.get("png_path")

    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
