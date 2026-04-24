#!/usr/bin/env python3
"""
fetch.py — 投资日报的统一行情数据入口。

设计目标:
1. Agent 只需要一条 Bash 命令就拿到 JSON,不用自己拼 Python。
2. 多源级联:sina → em → yfinance,任何一源失败自动换下一个。
3. 本地全失败时返回 {"status":"unavailable"},让 Agent 跳过这只,**不再 fallback 到 WebSearch**。
4. 所有子命令统一输出 JSON 到 stdout,出错输出 JSON 到 stdout 并退出码 0 — Agent 只看 JSON。

子命令:
  indices   --markets A,US,HK        拉指数(按市场)
  quotes    --symbols 600519.SS,NVDA 拉多只标的当日行情(跨市场)
  sectors                             拉 A 股行业板块涨跌榜
  search    --keyword 茅台            按中文名/代码搜 A 股,返回候选

Symbol 格式(全程用 yfinance 风格):
  A 股沪市: 600519.SS    A 股深市: 000858.SZ
  港股:     0700.HK       美股:    NVDA
  指数:     000001.SS(上证)/ 399001.SZ(深证)/ 399006.SZ(创业板) / ^IXIC(纳指) / ^GSPC(标普) / ^HSI(恒生)
"""

from __future__ import annotations

import argparse
import json
import sys
import warnings
from typing import Any

warnings.filterwarnings("ignore")

# ---------- 库探测 ----------

def _has(mod: str) -> bool:
    try:
        __import__(mod)
        return True
    except Exception:
        return False


HAS_AK = _has("akshare")
HAS_YF = _has("yfinance")


# ---------- 工具 ----------

def _out(obj: Any) -> None:
    """统一输出 JSON 到 stdout,不抛异常。"""
    print(json.dumps(obj, ensure_ascii=False, default=str))


def _pct(prev: float, cur: float) -> float:
    if prev == 0:
        return 0.0
    return float((cur - prev) / prev * 100)


# ---------- 指数 ----------

# 支持的指数:yfinance symbol → (中文名, akshare sina symbol, 市场)
INDEX_MAP = {
    "000001.SS": ("上证指数", "sh000001", "A"),
    "399001.SZ": ("深证成指", "sz399001", "A"),
    "399006.SZ": ("创业板指", "sz399006", "A"),
    "^IXIC":     ("纳斯达克综合", None,      "US"),
    "^GSPC":     ("标普500",    None,       "US"),
    "^HSI":      ("恒生指数",    None,      "HK"),
}

MARKET_DEFAULTS = {
    "A":  ["000001.SS", "399001.SZ", "399006.SZ"],
    "US": ["^IXIC", "^GSPC"],
    "HK": ["^HSI"],
}


def fetch_indices(markets: list[str]) -> dict:
    """按市场拉指数。A 股优先 akshare(sina),外盘优先 yfinance。"""
    wanted: list[str] = []
    for m in markets:
        wanted.extend(MARKET_DEFAULTS.get(m.upper(), []))
    wanted = list(dict.fromkeys(wanted))  # dedup preserving order

    out: dict[str, dict] = {}

    # ---- A 股指数:akshare 批量 spot(sina)----
    a_wanted = [s for s in wanted if INDEX_MAP[s][2] == "A"]
    if a_wanted and HAS_AK:
        try:
            import akshare as ak
            df = ak.stock_zh_index_spot_sina()
            name2row = {r["名称"]: r for _, r in df.iterrows()}
            for s in a_wanted:
                cn, _, _ = INDEX_MAP[s]
                if cn in name2row:
                    r = name2row[cn]
                    out[s] = {
                        "name": cn,
                        "price": float(r["最新价"]),
                        "change_pct": float(r["涨跌幅"]),
                        "source": "akshare.sina.spot",
                    }
        except Exception:
            pass

    # ---- A 股指数兜底:逐只 daily(sina)----
    for s in a_wanted:
        if s in out:
            continue
        if not HAS_AK:
            break
        cn, sina_sym, _ = INDEX_MAP[s]
        try:
            import akshare as ak
            df = ak.stock_zh_index_daily(symbol=sina_sym)
            cur, prev = df.iloc[-1], df.iloc[-2]
            out[s] = {
                "name": cn,
                "price": float(cur["close"]),
                "change_pct": _pct(float(prev["close"]), float(cur["close"])),
                "source": "akshare.sina.daily",
            }
        except Exception:
            pass

    # ---- 外盘指数:yfinance ----
    fx_wanted = [s for s in wanted if INDEX_MAP[s][2] in ("US", "HK") and s not in out]
    if fx_wanted and HAS_YF:
        try:
            import yfinance as yf
            for s in fx_wanted:
                cn, _, _ = INDEX_MAP[s]
                try:
                    t = yf.Ticker(s).history(period="2d")
                    if len(t) >= 2:
                        prev, cur = float(t["Close"].iloc[-2]), float(t["Close"].iloc[-1])
                        out[s] = {
                            "name": cn,
                            "price": cur,
                            "change_pct": _pct(prev, cur),
                            "source": "yfinance",
                        }
                except Exception:
                    continue
        except Exception:
            pass

    # ---- A 股指数的最后兜底:yfinance ----
    for s in a_wanted:
        if s in out or not HAS_YF:
            continue
        cn, _, _ = INDEX_MAP[s]
        try:
            import yfinance as yf
            t = yf.Ticker(s).history(period="2d")
            if len(t) >= 2:
                prev, cur = float(t["Close"].iloc[-2]), float(t["Close"].iloc[-1])
                out[s] = {
                    "name": cn,
                    "price": cur,
                    "change_pct": _pct(prev, cur),
                    "source": "yfinance",
                }
        except Exception:
            pass

    # ---- 仍没拿到的,标记 unavailable(不 fallback 到 WebSearch)----
    for s in wanted:
        if s not in out:
            out[s] = {"name": INDEX_MAP[s][0], "status": "unavailable"}

    return out


# ---------- 个股/ETF ----------

def _parse_symbol(sym: str) -> tuple[str, str]:
    """返回 (market, local_sym)。market ∈ {A-SH, A-SZ, HK, US}"""
    if sym.endswith(".SS"):
        return "A-SH", sym[:-3]
    if sym.endswith(".SZ"):
        return "A-SZ", sym[:-3]
    if sym.endswith(".HK"):
        return "HK", sym[:-3].lstrip("0").rjust(4, "0") if sym[:-3].isdigit() else sym[:-3]
    return "US", sym


def _fetch_a_single(local_sym: str, sh_or_sz: str) -> dict | None:
    """A 股单只:优先 akshare sina daily。"""
    if not HAS_AK:
        return None
    prefix = "sh" if sh_or_sz == "A-SH" else "sz"
    try:
        import akshare as ak
        df = ak.stock_zh_a_daily(symbol=f"{prefix}{local_sym}")
        cur, prev = df.iloc[-1], df.iloc[-2]
        return {
            "price": float(cur["close"]),
            "change_pct": _pct(float(prev["close"]), float(cur["close"])),
            "source": "akshare.sina.daily",
        }
    except Exception:
        return None


def _fetch_a_etf(local_sym: str) -> dict | None:
    """A 股 ETF:尝试 fund_etf_hist_sina。"""
    if not HAS_AK:
        return None
    try:
        import akshare as ak
        # sina ETF 也支持 sh/sz 前缀
        for prefix in ("sh", "sz"):
            try:
                df = ak.fund_etf_hist_sina(symbol=f"{prefix}{local_sym}")
                cur, prev = df.iloc[-1], df.iloc[-2]
                return {
                    "price": float(cur["close"]),
                    "change_pct": _pct(float(prev["close"]), float(cur["close"])),
                    "source": f"akshare.sina.etf.{prefix}",
                }
            except Exception:
                continue
    except Exception:
        return None
    return None


def _fetch_yf(sym: str) -> dict | None:
    if not HAS_YF:
        return None
    try:
        import yfinance as yf
        t = yf.Ticker(sym).history(period="2d")
        if len(t) >= 2:
            prev, cur = float(t["Close"].iloc[-2]), float(t["Close"].iloc[-1])
            return {
                "price": cur,
                "change_pct": _pct(prev, cur),
                "source": "yfinance",
            }
    except Exception:
        pass
    return None


def fetch_quotes(symbols: list[str]) -> dict:
    out: dict[str, dict] = {}
    for sym in symbols:
        market, local = _parse_symbol(sym)
        quote: dict | None = None

        if market in ("A-SH", "A-SZ"):
            # 尝试 1:A 股个股 daily
            quote = _fetch_a_single(local, market)
            # 尝试 2:A 股 ETF
            if quote is None:
                quote = _fetch_a_etf(local)
            # 尝试 3:yfinance
            if quote is None:
                quote = _fetch_yf(sym)
        elif market in ("HK", "US"):
            quote = _fetch_yf(sym)

        if quote is None:
            out[sym] = {"status": "unavailable"}
        else:
            out[sym] = quote
    return out


# ---------- 板块 ----------

def fetch_sectors(top_n: int = 10) -> dict:
    """拉行业板块涨跌榜,取领涨/领跌各 top_n。多源级联:em → sina。"""
    if not HAS_AK:
        return {"status": "unavailable", "hint": "pip install akshare"}
    import akshare as ak

    # 方案 1: em(列名:板块名称 / 涨跌幅)
    try:
        df = ak.stock_board_industry_name_em()
        col_name = "板块名称" if "板块名称" in df.columns else df.columns[1]
        col_pct = "涨跌幅" if "涨跌幅" in df.columns else next(c for c in df.columns if "涨跌" in c)
        df = df.sort_values(col_pct, ascending=False)
        top = df.head(top_n)[[col_name, col_pct]].rename(columns={col_name: "name", col_pct: "change_pct"}).to_dict(orient="records")
        bottom = df.tail(top_n).sort_values(col_pct)[[col_name, col_pct]].rename(columns={col_name: "name", col_pct: "change_pct"}).to_dict(orient="records")
        return {"top": top, "bottom": bottom, "source": "akshare.em.industry"}
    except Exception:
        pass

    # 方案 2: stock_sector_spot(sina)— 列名:label / 板块 / 涨跌幅
    try:
        df = ak.stock_sector_spot()
        col_name = "板块" if "板块" in df.columns else df.columns[1]
        col_pct = "涨跌幅" if "涨跌幅" in df.columns else next(c for c in df.columns if "涨跌" in c)
        df = df.copy()
        df[col_pct] = df[col_pct].astype(str).str.rstrip("%").astype(float)
        df = df.sort_values(col_pct, ascending=False)
        top = df.head(top_n)[[col_name, col_pct]].rename(columns={col_name: "name", col_pct: "change_pct"}).to_dict(orient="records")
        bottom = df.tail(top_n).sort_values(col_pct)[[col_name, col_pct]].rename(columns={col_name: "name", col_pct: "change_pct"}).to_dict(orient="records")
        return {"top": top, "bottom": bottom, "source": "akshare.sina.sector"}
    except Exception as e:
        return {"status": "error", "error": str(e)[:200]}


# ---------- 股票搜索 ----------

def search_stock(keyword: str, limit: int = 5) -> dict:
    """按中文名/代码搜 A 股。多源级联:sina 交易所名单 → em 静态名单 → em 单只直查。"""
    if not HAS_AK:
        return {"status": "unavailable", "hint": "pip install akshare"}
    import akshare as ak
    results: list[dict] = []
    seen: set[str] = set()

    # 方案 1: sina 上交所 + 深交所名单(稳定、快)
    for fn_name, code_col, name_col, suffix in (
        ("stock_info_sh_name_code", "证券代码", "证券简称", ".SS"),
        ("stock_info_sz_name_code", "A股代码",  "A股简称",  ".SZ"),
    ):
        if len(results) >= limit:
            break
        try:
            df = getattr(ak, fn_name)()
            mask = df[name_col].astype(str).str.contains(keyword, na=False) | df[code_col].astype(str).str.contains(keyword, na=False)
            for _, r in df[mask].head(limit - len(results)).iterrows():
                code = str(r[code_col])
                if code in seen:
                    continue
                seen.add(code)
                results.append({"code": code, "name": r[name_col], "yfinance_symbol": code + suffix,
                                "source": f"akshare.sina.{fn_name}"})
        except Exception:
            continue

    if results:
        return {"results": results}

    # 方案 2: em 静态名单
    try:
        df = ak.stock_info_a_code_name()
        col_code = "code" if "code" in df.columns else "代码"
        col_name = "name" if "name" in df.columns else "名称"
        mask = df[col_name].astype(str).str.contains(keyword, na=False) | df[col_code].astype(str).str.contains(keyword, na=False)
        hits = df[mask].head(limit)
        if len(hits) > 0:
            for _, r in hits.iterrows():
                code = str(r[col_code])
                yf_sym = f"{code}.SS" if code.startswith(("60", "68", "51", "58", "90")) else f"{code}.SZ"
                results.append({"code": code, "name": r[col_name], "yfinance_symbol": yf_sym,
                                "source": "akshare.em.code_name"})
            return {"results": results}
    except Exception:
        pass

    # 方案 3: keyword 是 6 位纯代码 → 单只直查
    if keyword.isdigit() and len(keyword) == 6:
        try:
            info = ak.stock_individual_info_em(symbol=keyword)
            name_row = info[info["item"] == "股票简称"]
            if len(name_row):
                name = str(name_row["value"].iloc[0])
                yf_sym = f"{keyword}.SS" if keyword.startswith(("60", "68", "51", "58", "90")) else f"{keyword}.SZ"
                return {"results": [{"code": keyword, "name": name, "yfinance_symbol": yf_sym,
                                     "source": "akshare.em.individual"}]}
        except Exception:
            pass

    return {"results": [], "status": "not_found"}


# ---------- 并行快照(一次拿齐指数+自选+板块) ----------

def fetch_snapshot(markets: list[str], watchlist: list[str], need_sectors: bool, sector_top: int = 10) -> dict:
    """并行调用 indices / quotes / sectors,合并结果。

    三者互相独立,用 ThreadPoolExecutor 并行,总耗时 ≈ max(三者耗时)。
    """
    from concurrent.futures import ThreadPoolExecutor

    tasks: dict[str, "callable"] = {}
    if markets:
        tasks["indices"] = lambda: fetch_indices(markets)
    if watchlist:
        tasks["quotes"] = lambda: fetch_quotes(watchlist)
    if need_sectors:
        tasks["sectors"] = lambda: fetch_sectors(top_n=sector_top)

    results: dict[str, dict] = {}
    if not tasks:
        return {"has_akshare": HAS_AK, "has_yfinance": HAS_YF, **results}

    with ThreadPoolExecutor(max_workers=len(tasks)) as pool:
        futures = {name: pool.submit(fn) for name, fn in tasks.items()}
        for name, fut in futures.items():
            try:
                results[name] = fut.result(timeout=30)
            except Exception as e:
                results[name] = {"status": "error", "error": str(e)[:200]}

    return {"has_akshare": HAS_AK, "has_yfinance": HAS_YF, **results}


# ---------- 主入口 ----------

def main() -> None:
    p = argparse.ArgumentParser(description="投资日报统一行情数据入口")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_idx = sub.add_parser("indices", help="按市场拉指数")
    p_idx.add_argument("--markets", default="A", help="逗号分隔: A,US,HK")

    p_q = sub.add_parser("quotes", help="批量拉多只标的当日行情")
    p_q.add_argument("--symbols", required=True, help="yfinance 风格逗号分隔: 600519.SS,NVDA,0700.HK")

    p_s = sub.add_parser("sectors", help="A 股行业板块涨跌榜")
    p_s.add_argument("--top", type=int, default=10)

    p_search = sub.add_parser("search", help="按关键词搜 A 股代码")
    p_search.add_argument("--keyword", required=True)
    p_search.add_argument("--limit", type=int, default=5)

    p_env = sub.add_parser("env", help="探测本地依赖可用性")

    p_snap = sub.add_parser("snapshot", help="并行拉取 指数+自选+板块(日报专用,一次搞定)")
    p_snap.add_argument("--markets", default="A", help="逗号分隔市场: A,US,HK")
    p_snap.add_argument("--watchlist", default="", help="yfinance 风格 symbol 逗号分隔; 空则不拉自选")
    p_snap.add_argument("--sectors", action="store_true", help="加此 flag 同时拉板块榜")
    p_snap.add_argument("--sector-top", type=int, default=10)

    args = p.parse_args()

    if args.cmd == "indices":
        _out({"has_akshare": HAS_AK, "has_yfinance": HAS_YF,
              "data": fetch_indices([m.strip() for m in args.markets.split(",") if m.strip()])})
    elif args.cmd == "quotes":
        _out({"has_akshare": HAS_AK, "has_yfinance": HAS_YF,
              "data": fetch_quotes([s.strip() for s in args.symbols.split(",") if s.strip()])})
    elif args.cmd == "sectors":
        _out(fetch_sectors(top_n=args.top))
    elif args.cmd == "search":
        _out(search_stock(args.keyword, limit=args.limit))
    elif args.cmd == "env":
        _out({"has_akshare": HAS_AK, "has_yfinance": HAS_YF})
    elif args.cmd == "snapshot":
        _out(fetch_snapshot(
            markets=[m.strip() for m in args.markets.split(",") if m.strip()],
            watchlist=[s.strip() for s in args.watchlist.split(",") if s.strip()],
            need_sectors=args.sectors,
            sector_top=args.sector_top,
        ))
    else:
        _out({"status": "error", "error": f"unknown cmd: {args.cmd}"})


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        _out({"status": "error", "error": str(e)[:300]})
