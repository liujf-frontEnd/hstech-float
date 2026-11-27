# -*- coding: utf-8 -*-
"""
低调桌面浮窗：恒科 + 上证 + 自选基金/股票估值与盈亏
- 无边框置顶、半透明、可拖动
- 开盘短间隔刷新；双边收盘后降频
"""
from __future__ import annotations

import csv
import json
import re
import shutil
import ssl
import subprocess
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, time as dtime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from pathlib import Path

try:
    import tkinter as tk
    from tkinter import Menu, messagebox
except ImportError as e:
    raise SystemExit("需要 tkinter（通常随 Python 自带）") from e

# ---------- 配置 ----------
POLL_OPEN_SEC = 4.0
POLL_CLOSED_SEC = 900.0
ALPHA = 0.82
WIN_W, WIN_H = 150, 118  # 初始值；首次绘制后按文字收紧
MARGIN = 16
TZ_SH = timezone(timedelta(hours=8))
HOLDINGS_SOURCE = "天天基金/东财 F10"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
SSL_CTX = ssl.create_default_context()

Holding = Tuple[str, str, str, float]  # market, code, name, weight%


def _H(market: str, code: str, name: str, w: float) -> Holding:
    return (market, code, name, w)


# 017435 华宝中证沪港深新消费指数C — 2026年2季度 / 2026-06-30，约 94%
H_017435: List[Holding] = [
    _H("hk", "00700", "腾讯控股", 15.09),
    _H("hk", "09988", "阿里巴巴-W", 12.37),
    _H("hk", "03690", "美团-W", 12.03),
    _H("hk", "01810", "小米集团-W", 11.13),
    _H("sz", "002602", "世纪华通", 3.75),
    _H("sz", "002230", "科大讯飞", 3.60),
    _H("hk", "09992", "泡泡玛特", 3.54),
    _H("sh", "601888", "中国中免", 2.61),
    _H("sh", "688111", "金山办公", 2.46),
    _H("sz", "002558", "巨人网络", 1.82),
    _H("hk", "06618", "京东健康", 1.82),
    _H("sz", "300418", "昆仑万维", 1.81),
    _H("sz", "002555", "三七互娱", 1.45),
    _H("sz", "002517", "恺英网络", 1.38),
    _H("hk", "03888", "金山软件", 1.06),
    _H("sh", "688169", "石头科技", 0.98),
    _H("hk", "00241", "阿里健康", 0.86),
    _H("sz", "300628", "亿联网络", 0.85),
    _H("sz", "002624", "完美世界", 0.84),
    _H("sz", "300251", "光线传媒", 0.81),
    _H("sh", "603444", "吉比特", 0.77),
    _H("sz", "300002", "神州泰岳", 0.76),
    _H("hk", "00780", "同程旅行", 0.72),
    _H("sh", "603605", "珀莱雅", 0.71),
    _H("sz", "300896", "爱美客", 0.66),
    _H("hk", "02367", "巨子生物", 0.61),
    _H("sh", "603486", "科沃斯", 0.58),
    _H("sz", "300773", "拉卡拉", 0.58),
    _H("hk", "02400", "心动公司", 0.56),
    _H("sz", "300413", "芒果超媒", 0.54),
    _H("sh", "603939", "益丰药房", 0.54),
    _H("sz", "300315", "掌趣科技", 0.53),
    _H("hk", "01797", "东方甄选", 0.52),
    _H("sz", "300182", "捷成股份", 0.50),
    _H("sz", "300133", "华策影视", 0.47),
    _H("sh", "688363", "华熙生物", 0.43),
    _H("hk", "00772", "阅文集团", 0.42),
    _H("sz", "300130", "新国都", 0.42),
    _H("sh", "600633", "浙数文化", 0.39),
    _H("sz", "301606", "绿联科技", 0.38),
    _H("sh", "688802", "沐曦股份", 0.35),
    _H("sz", "300957", "贝泰妮", 0.33),
    _H("hk", "01833", "平安好医生", 0.33),
    _H("sz", "002032", "苏泊尔", 0.32),
    _H("sh", "600315", "上海家化", 0.28),
    _H("sz", "002891", "中宠股份", 0.26),
    _H("sz", "301498", "乖宝宠物", 0.24),
    _H("hk", "01060", "大麦娱乐", 0.24),
    _H("hk", "01318", "毛戈平", 0.15),
    _H("sh", "603355", "莱克电气", 0.15),
]

# 161725 招商中证白酒指数(LOF)A — 2026年2季度 / 2026-06-30，约 94.8%（仅保留权重>0）
H_161725: List[Holding] = [
    _H("sh", "600519", "贵州茅台", 17.28),
    _H("sh", "600809", "山西汾酒", 15.19),
    _H("sz", "000568", "泸州老窖", 15.03),
    _H("sz", "000858", "五粮液", 14.22),
    _H("sz", "002304", "洋河股份", 7.88),
    _H("sz", "000596", "古井贡酒", 4.86),
    _H("sh", "603369", "今世缘", 4.67),
    _H("sh", "603198", "迎驾贡酒", 2.72),
    _H("sz", "000799", "酒鬼酒", 2.23),
    _H("sh", "600702", "舍得酒业", 1.87),
    _H("sh", "600779", "水井坊", 1.85),
    _H("sh", "603589", "口子窖", 1.77),
    _H("sh", "600559", "老白干酒", 1.62),
    _H("sh", "603919", "金徽酒", 1.21),
    _H("sz", "000860", "顺鑫农业", 1.15),
    _H("sh", "600199", "金种子酒", 0.64),
    _H("sh", "600197", "伊力特", 0.28),
    _H("sz", "000995", "皇台酒业", 0.17),
    _H("sh", "688981", "中芯国际", 0.12),
    _H("sh", "601658", "邮储银行", 0.01),
]

# 011612 华夏科创50ETF联接A — 联接基金：目标 ETF 588000（资产配置「其他」约 92.95%）
# + 少量成分股直投（约 1.55%），2026-06-30
H_011612: List[Holding] = [
    _H("sh", "588000", "科创50ETF华夏", 92.95),
    _H("sh", "688256", "寒武纪", 0.16),
    _H("sh", "688008", "澜起科技", 0.12),
    _H("sh", "688041", "海光信息", 0.12),
    _H("sh", "688012", "中微公司", 0.11),
    _H("sh", "688981", "中芯国际", 0.11),
    _H("sh", "688072", "拓荆科技", 0.10),
    _H("sh", "688795", "摩尔线程", 0.07),
    _H("sh", "688525", "佰维存储", 0.07),
    _H("sh", "688521", "芯原股份", 0.06),
    _H("sh", "688120", "华海清科", 0.05),
    _H("sh", "688498", "源杰科技", 0.04),
    _H("sh", "688361", "中科飞测", 0.03),
    _H("sh", "688777", "中控技术", 0.03),
    _H("sh", "688802", "沐曦股份", 0.03),
    _H("sh", "688126", "沪硅产业", 0.03),
    _H("sh", "688249", "晶合集成", 0.02),
    _H("sh", "688347", "华虹宏力", 0.02),
    _H("sh", "688469", "芯联集成", 0.02),
    _H("sh", "688396", "华润微", 0.02),
    _H("sh", "688082", "盛美上海", 0.02),
    _H("sh", "688271", "联影医疗", 0.02),
    _H("sh", "688111", "金山办公", 0.02),
    _H("sh", "688702", "盛科通信", 0.02),
    _H("sh", "688027", "国盾量子", 0.02),
    _H("sh", "688099", "晶晨股份", 0.02),
    _H("sh", "688183", "生益电子", 0.01),
    _H("sh", "688036", "传音控股", 0.01),
    _H("sh", "688220", "翱捷科技", 0.01),
    _H("sh", "688047", "龙芯中科", 0.01),
    _H("sh", "688213", "思特威", 0.01),
    _H("sh", "688506", "百利天恒", 0.01),
    _H("sh", "688578", "艾力斯", 0.01),
    _H("sh", "688122", "西部超导", 0.01),
    _H("sh", "689009", "九号公司", 0.01),
    _H("sh", "688608", "恒玄科技", 0.01),
    _H("sh", "688169", "石头科技", 0.01),
    _H("sh", "688599", "天合光能", 0.01),
    _H("sh", "688223", "晶科能源", 0.01),
    _H("sh", "688375", "国博电子", 0.01),
    _H("sh", "688728", "格科微", 0.01),
    _H("sh", "688617", "惠泰医疗", 0.01),
    _H("sh", "688187", "时代电气", 0.01),
    _H("sh", "688065", "凯赛生物", 0.01),
    _H("sh", "688188", "柏楚电子", 0.01),
    _H("sh", "688472", "阿特斯", 0.01),
    _H("sh", "688538", "和辉光电", 0.01),
    _H("sh", "688568", "中科星图", 0.01),
]

FUNDS = [
    {
        "code": "017435",
        "label": "港股消费",
        "name": "华宝中证沪港深新消费指数C",
        "period": "2026年2季度",
        "asof": "2026-06-30",
        "holdings": H_017435,
        "feeder_etf": None,  # 普通股票指数基金
    },
    {
        "code": "161725",
        "label": "白酒",
        "name": "招商中证白酒指数(LOF)A",
        "period": "2026年2季度",
        "asof": "2026-06-30",
        "holdings": H_161725,
        "feeder_etf": None,
    },
    {
        "code": "011612",
        "label": "科创50",
        "name": "华夏科创50ETF联接A",
        "period": "2026年2季度",
        "asof": "2026-06-30",
        # 联接基金：目标 ETF 占绝大多数（资产配置「其他」≈92.95%）
        "holdings": H_011612,
        "feeder_etf": ("sh", "588000", 92.95),
    },
]


def now_shanghai() -> datetime:
    return datetime.now(TZ_SH)


def is_hk_session(dt: Optional[datetime] = None) -> bool:
    dt = dt or now_shanghai()
    if dt.weekday() >= 5:
        return False
    t = dt.time()
    return (dtime(9, 30) <= t <= dtime(12, 0)) or (dtime(13, 0) <= t <= dtime(16, 0))


def is_cn_session(dt: Optional[datetime] = None) -> bool:
    dt = dt or now_shanghai()
    if dt.weekday() >= 5:
        return False
    t = dt.time()
    return (dtime(9, 30) <= t <= dtime(11, 30)) or (dtime(13, 0) <= t <= dtime(15, 0))


def is_market_open(dt: Optional[datetime] = None) -> bool:
    return is_hk_session(dt) or is_cn_session(dt)


_CREATE_NO_WINDOW = 0x08000000  # 避免 pythonw 调 curl 时闪出黑窗


def _http_get(url: str, *, encoding: str = "utf-8", extra_headers: Optional[dict] = None) -> str:
    headers = {"User-Agent": UA, "Accept": "*/*"}
    if extra_headers:
        headers.update(extra_headers)
    last_err: Optional[BaseException] = None
    for attempt in range(2):
        try:
            return _http_get_urllib(url, encoding=encoding, headers=headers)
        except Exception as e:
            last_err = e
            if attempt == 0:
                time.sleep(0.15)
    # Windows 常见本地代理（Clash 等 Fake-IP / TUN）会对连接做 TLS 重协商。
    # Python urllib 走 OpenSSL，经常被对端直接断开；系统 curl.exe 走 Schannel，通常可通。
    try:
        return _http_get_curl(url, encoding=encoding, headers=headers)
    except Exception:
        if last_err is not None:
            raise last_err
        raise


def _http_get_urllib(url: str, *, encoding: str, headers: dict) -> str:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=10, context=SSL_CTX) as resp:
        return resp.read().decode(encoding, errors="replace")


def _http_get_curl(url: str, *, encoding: str, headers: dict) -> str:
    curl = shutil.which("curl.exe") or shutil.which("curl")
    if not curl:
        raise FileNotFoundError("curl not found")
    # HTTP/2 + Schannel 在部分网络上会被对端直接掐断（curl 56 missing close_notify）
    cmd = [curl, "-sS", "-L", "--http1.1", "--no-keepalive", "--max-time", "10", "--connect-timeout", "8"]
    for k, v in headers.items():
        lk = k.lower()
        if lk == "user-agent":
            cmd.extend(["-A", str(v)])
        elif lk == "referer":
            cmd.extend(["-e", str(v)])
        else:
            cmd.extend(["-H", f"{k}: {v}"])
    cmd.append(url)
    kwargs: dict = {"capture_output": True, "timeout": 12}
    if sys.platform == "win32":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", _CREATE_NO_WINDOW)
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        kwargs["startupinfo"] = si
    p = subprocess.run(cmd, **kwargs)
    if p.returncode != 0:
        err = (p.stderr or b"").decode("utf-8", errors="replace").strip()[:240]
        raise OSError(f"curl exit {p.returncode}: {err or 'no stderr'}")
    raw = p.stdout or b""
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    return raw.decode(encoding, errors="replace")


def _sina_batch(codes: List[str]) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {}
    if not codes:
        return out
    for i in range(0, len(codes), 60):
        chunk = codes[i : i + 60]
        url = "https://hq.sinajs.cn/list=" + ",".join(chunk)
        text = _http_get(
            url,
            encoding="gbk",
            extra_headers={"Referer": "https://finance.sina.com.cn"},
        )
        for line in text.splitlines():
            m = re.search(r"hq_str_([^=]+)=\"([^\"]*)\"", line)
            if not m or not m.group(2):
                continue
            out[m.group(1)] = m.group(2).split(",")
    return out


def _pct_from_hk(fields: List[str]) -> Tuple[float, float, float]:
    return float(fields[6]), float(fields[7]), float(fields[8])


def _pct_from_a(fields: List[str]) -> Tuple[float, float, float]:
    prev = float(fields[2])
    price = float(fields[3])
    if price <= 0 or prev <= 0:
        raise ValueError("a-share bad")
    change = price - prev
    return price, change, change / prev * 100.0


def _pct_from_s_index(fields: List[str]) -> Tuple[float, float, float]:
    return float(fields[1]), float(fields[2]), float(fields[3])


def fetch_hstech(batch: Dict[str, List[str]]) -> Tuple[float, float, float]:
    return _pct_from_hk(batch["rt_hkHSTECH"])


def fetch_shanghai(batch: Dict[str, List[str]]) -> Tuple[float, float, float]:
    return _pct_from_s_index(batch["s_sh000001"])


def fetch_fund_nav(code: str) -> Tuple[float, str]:
    """最新已公布净值（可能是当日官方，收盘后会变成今天）。"""
    rows = fetch_fund_lsjz(code, page_size=3)
    if not rows:
        raise ValueError("nav empty")
    return float(rows[0]["DWJZ"]), str(rows[0]["FSRQ"])


def fetch_prev_nav_for_estimate(
    code: str, *, trade_date: Optional[str] = None
) -> Tuple[float, str]:
    """估值用基准净值：必须严格早于当日交易日，避免官方公布后叠加上当日涨跌。"""
    today = trade_date or _trade_date_str()
    rows = fetch_fund_lsjz(code, page_size=10)
    if not rows:
        raise ValueError("nav empty")
    for row in rows:
        day = str(row.get("FSRQ") or "")
        if day and day < today:
            return float(row["DWJZ"]), day
    # 仅有当日或更早缺失时，退回最新一条
    return float(rows[0]["DWJZ"]), str(rows[0]["FSRQ"])


def fetch_fund_lsjz(code: str, page_size: int = 15) -> List[dict]:
    """东财历史净值列表（新→旧）。含 DWJZ / FSRQ / JZZZL。"""
    url = (
        "https://api.fund.eastmoney.com/f10/lsjz"
        f"?fundCode={code}&pageIndex=1&pageSize={page_size}"
    )
    text = _http_get(url, extra_headers={"Referer": "https://fundf10.eastmoney.com/"})
    return list((json.loads(text).get("Data") or {}).get("LSJZList") or [])


def _trade_date_str(dt: Optional[datetime] = None) -> str:
    return (dt or now_shanghai()).strftime("%Y-%m-%d")


# 收盘估值落盘时刻（Asia/Shanghai）
SNAP_CN_TIME = dtime(15, 5)   # A 股为主
SNAP_HK_TIME = dtime(16, 10)  # 港股/恒科相关，等港股收盘后再记


def fund_is_hk_heavy(
    holdings: Optional[List[Holding]] = None,
    *,
    fund: Optional[dict] = None,
    label: str = "",
    name: str = "",
) -> bool:
    """
    是否按港股收盘节奏落盘：
    - 名称/标签含港股、恒生、恒科、HSTECH、沪港深等；或
    - 持仓中港股权重合计 ≥ 30%；或
    - 目标 ETF / 任意持仓标的为港股且权重偏大。
    """
    blob = f"{label or ''}{name or ''}{(fund or {}).get('label') or ''}{(fund or {}).get('name') or ''}"
    for kw in ("港股", "恒生", "恒科", "HSTECH", "hstech", "沪港深", "港股通", "Hang Seng", "HSI"):
        if kw in blob:
            return True
    hs = list(holdings or [])
    if not hs and fund:
        hs = list(fund.get("holdings") or [])
    hk_w = sum(float(h[3]) for h in hs if h and h[0] == "hk")
    if hk_w >= 30.0:
        return True
    # 联接目标若是港股 ETF
    feeder = (fund or {}).get("feeder_etf")
    if feeder and len(feeder) >= 3 and feeder[0] == "hk" and float(feeder[2]) >= 30.0:
        return True
    return False


def snapshot_cutoff_for_fund(
    holdings: Optional[List[Holding]] = None,
    *,
    fund: Optional[dict] = None,
    label: str = "",
    name: str = "",
) -> dtime:
    """返回该基金今日可落盘的最早时刻（上海时区）。"""
    if fund_is_hk_heavy(holdings, fund=fund, label=label, name=name):
        return SNAP_HK_TIME
    return SNAP_CN_TIME


def should_snapshot_close_for_fund(
    holdings: Optional[List[Holding]] = None,
    *,
    fund: Optional[dict] = None,
    label: str = "",
    name: str = "",
    dt: Optional[datetime] = None,
) -> bool:
    """按基金类型判断当前是否已过收盘落盘窗口。"""
    dt = dt or now_shanghai()
    if dt.weekday() >= 5:
        return False
    cutoff = snapshot_cutoff_for_fund(holdings, fund=fund, label=label, name=name)
    return dt.time() >= cutoff


def should_snapshot_close(dt: Optional[datetime] = None) -> bool:
    """兼容旧调用：任一类型窗口已到（≥15:05）即 True；真正写入仍按基金逐条判断。"""
    dt = dt or now_shanghai()
    if dt.weekday() >= 5:
        return False
    return dt.time() >= SNAP_CN_TIME


def _ensure_est_log() -> None:
    if EST_LOG_PATH.exists():
        return
    with EST_LOG_PATH.open("w", encoding="utf-8-sig", newline="") as f:
        csv.DictWriter(f, fieldnames=EST_LOG_FIELDS).writeheader()


def read_est_log() -> List[dict]:
    _ensure_est_log()
    with EST_LOG_PATH.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _write_est_log(rows: List[dict]) -> None:
    _ensure_est_log()
    with EST_LOG_PATH.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=EST_LOG_FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in EST_LOG_FIELDS})


def est_log_has(date_s: str, code: str) -> bool:
    for r in read_est_log():
        if r.get("date") == date_s and r.get("code") == code:
            return True
    return False


def append_close_estimate(
    *,
    date_s: str,
    code: str,
    label: str,
    est_pct: float,
    est_nav: Optional[float],
    prev_nav: Optional[float],
    nav_date: str,
    covered: float,
    used: int,
    force: bool = False,
) -> bool:
    """写入一日一基一行；已存在则跳过（除非 force）。"""
    _ensure_est_log()
    rows = read_est_log()
    for r in rows:
        if r.get("date") == date_s and r.get("code") == code:
            if not force:
                return False
            # force：只更新估值字段，保留已填官方
            r["label"] = label
            r["est_pct"] = f"{est_pct:.6f}"
            r["est_nav"] = "" if est_nav is None else f"{float(est_nav):.6f}"
            r["prev_nav"] = "" if prev_nav is None else f"{float(prev_nav):.6f}"
            r["nav_date"] = nav_date or ""
            r["covered"] = f"{covered:.2f}"
            r["used"] = str(int(used))
            r["snap_time"] = now_shanghai().strftime("%Y-%m-%d %H:%M:%S")
            if r.get("official_nav"):
                try:
                    on = float(r["official_nav"])
                    en = float(est_nav) if est_nav is not None else None
                    op = float(r["official_pct"]) if r.get("official_pct") not in ("", None) else None
                    r["err_pct"] = "" if op is None else f"{op - est_pct:.6f}"
                    r["err_nav"] = "" if en is None else f"{on - en:.6f}"
                except Exception:
                    pass
            _write_est_log(rows)
            return True
    row = {k: "" for k in EST_LOG_FIELDS}
    row.update(
        {
            "date": date_s,
            "code": code,
            "label": label,
            "est_pct": f"{est_pct:.6f}",
            "est_nav": "" if est_nav is None else f"{float(est_nav):.6f}",
            "prev_nav": "" if prev_nav is None else f"{float(prev_nav):.6f}",
            "nav_date": nav_date or "",
            "covered": f"{covered:.2f}",
            "used": str(int(used)),
            "snap_time": now_shanghai().strftime("%Y-%m-%d %H:%M:%S"),
        }
    )
    rows.append(row)
    _write_est_log(rows)
    return True


def fill_official_for_log(max_days: int = 30) -> int:
    """用东财 lsjz 回填未写官方净值的行；返回更新条数。"""
    rows = read_est_log()
    if not rows:
        return 0
    # 按 code 分组拉取
    need_codes = sorted(
        {
            r["code"]
            for r in rows
            if r.get("code") and not (r.get("official_nav") or "").strip()
        }
    )
    cache: Dict[str, List[dict]] = {}
    for code in need_codes:
        try:
            cache[code] = fetch_fund_lsjz(code, page_size=max(20, max_days + 5))
        except Exception:
            cache[code] = []
    updated = 0
    now_s = now_shanghai().strftime("%Y-%m-%d %H:%M:%S")
    for r in rows:
        if (r.get("official_nav") or "").strip():
            continue
        code = r.get("code") or ""
        date_s = r.get("date") or ""
        if not code or not date_s:
            continue
        hit = None
        for row in cache.get(code) or []:
            if str(row.get("FSRQ") or "") == date_s:
                hit = row
                break
        if not hit:
            continue
        try:
            official_nav = float(hit["DWJZ"])
        except Exception:
            continue
        # 官方日涨跌：优先 JZZZL，否则用 prev_nav 推算
        official_pct = None
        jzzzl = hit.get("JZZZL")
        if jzzzl not in (None, ""):
            try:
                official_pct = float(jzzzl)
            except Exception:
                official_pct = None
        if official_pct is None:
            try:
                pn = float(r["prev_nav"]) if r.get("prev_nav") else None
                if pn and pn > 0:
                    official_pct = (official_nav / pn - 1.0) * 100.0
            except Exception:
                pass
        try:
            est_pct = float(r["est_pct"]) if r.get("est_pct") else None
        except Exception:
            est_pct = None
        try:
            est_nav = float(r["est_nav"]) if r.get("est_nav") else None
        except Exception:
            est_nav = None
        r["official_nav"] = f"{official_nav:.6f}"
        r["official_pct"] = "" if official_pct is None else f"{official_pct:.6f}"
        r["official_date"] = date_s
        r["err_pct"] = (
            ""
            if est_pct is None or official_pct is None
            else f"{official_pct - est_pct:.6f}"
        )
        r["err_nav"] = (
            "" if est_nav is None else f"{official_nav - est_nav:.6f}"
        )
        r["filled_at"] = now_s
        updated += 1
    if updated:
        _write_est_log(rows)
    return updated


def parse_f10_stock_holdings(code: str) -> Optional[List[Holding]]:
    try:
        url = (
            "https://fundf10.eastmoney.com/FundArchivesDatas.aspx"
            f"?type=jjcc&code={code}&topline=50&year=&month=&rt=0.1"
        )
        text = _http_get(url, extra_headers={"Referer": "https://fundf10.eastmoney.com/"})
        sections = re.split(r"<h4 class='t'>", text)
        if len(sections) < 2:
            return None
        rows = re.findall(
            r"unify/r/(\d+)\.([0-9]+)'>([0-9]+)</a></td>"
            r"<td[^>]*><a[^>]*>([^<]+)</a>.*?<td[^>]*>([\d.]+)%",
            sections[1],
            re.S,
        )
        out: List[Holding] = []
        for mkt_s, _full, c, name, pct_s in rows:
            w = float(pct_s)
            if w <= 0:
                continue
            mkt = int(mkt_s)
            if mkt == 116:
                market, code_n = "hk", c.zfill(5)
            elif mkt == 0:
                market, code_n = "sz", c.zfill(6)
            elif mkt == 1:
                market, code_n = "sh", c.zfill(6)
            else:
                continue
            out.append((market, code_n, name, w))
        return out or None
    except Exception:
        return None


def fetch_other_asset_pct(code: str) -> Optional[float]:
    """从东财 pingzhongdata 资产配置推算「其他」占比（联接基金的目标 ETF 通常在此）。"""
    try:
        raw = _http_get(
            f"http://fund.eastmoney.com/pingzhongdata/{code}.js",
            extra_headers={"Referer": "https://fund.eastmoney.com/"},
        )
        m = re.search(r"Data_assetAllocation\s*=\s*(\{.*?\});", raw, re.S)
        if not m:
            return None
        obj = json.loads(m.group(1))
        stock = bond = cash = 0.0
        for s in obj.get("series") or []:
            n = str(s.get("name") or "")
            data = s.get("data") or []
            if not data:
                continue
            try:
                v = float(data[-1])
            except Exception:
                continue
            if "股票" in n:
                stock = v
            elif "债券" in n:
                bond = v
            elif "现金" in n:
                cash = v
        other = 100.0 - stock - bond - cash
        return other if other > 1.0 else None
    except Exception:
        return None


def _sina_suggest(key: str) -> List[Tuple[str, str, str]]:
    """新浪联想：[(code, name, type_code), ...]。"""
    try:
        from urllib.parse import quote

        url = (
            "https://suggest3.sinajs.cn/suggest/type=11,12,13,14,15,21,22,23,24,25,26&key="
            + quote(key)
        )
        text = _http_get(
            url,
            encoding="gbk",
            extra_headers={"Referer": "https://finance.sina.com.cn"},
        )
        m = re.search(r'="([^"]*)"', text)
        if not m or not m.group(1):
            return []
        out: List[Tuple[str, str, str]] = []
        for part in m.group(1).split(";"):
            if not part.strip():
                continue
            f = part.split(",")
            if len(f) < 4:
                continue
            code = (f[2] or "").strip()
            name = (f[0] or f[4] or "").strip()
            typ = (f[1] or "").strip()
            if code:
                out.append((code, name, typ))
        return out
    except Exception:
        return []


def _etf_market(code: str) -> str:
    c = code.zfill(6)
    if c.startswith(("5", "6", "9")):
        return "sh"
    return "sz"


def detect_feeder_etf(code: str, name: str) -> Optional[Tuple[str, str, float]]:
    """
    联接基金：解析目标 ETF 与「其他」权重。
    返回 (market, etf_code, weight%) 或 None。
    """
    name = name or ""
    other = fetch_other_asset_pct(code)
    if other is None:
        other = 92.0  # 联接常见默认；仍需找到 ETF 代码才使用
    # 去掉联接后缀再搜上市 ETF
    base = re.sub(r"联接[ABC]?$", "", name).strip()
    base = re.sub(r"[（(]LOF[)）]", "", base).strip()
    queries = []
    if base:
        queries.append(base)
    # 「易方达中证人工智能主题ETF」→ 再试去管理人后的主题
    m = re.match(r"^([一-鿿]{2,4})(.+)$", base)
    if m:
        mgr, rest = m.group(1), m.group(2)
        queries.append(rest)
        queries.append(rest.replace("ETF", "") + "ETF" + mgr)
    seen_q = set()
    candidates: List[Tuple[str, str, str]] = []
    for q in queries:
        if not q or q in seen_q:
            continue
        seen_q.add(q)
        for c, n, typ in _sina_suggest(q):
            if c == code:
                continue
            if "联接" in n:
                continue
            c6 = re.sub(r"\D", "", c).zfill(6)[-6:]
            # 场内 ETF / 基金：15/51/56/58 或新浪 type 22
            if not (c6.startswith(("15", "51", "56", "58")) or typ == "22"):
                continue
            candidates.append((c6, n, typ))
        if candidates:
            break
    if not candidates:
        return None
    etf_code, etf_name, _typ = candidates[0]
    return (_etf_market(etf_code), etf_code, float(other))


def refresh_fund_holdings(fund: dict) -> List[Holding]:
    """刷新持仓：普通基金用 F10 股票；联接基金自动补目标 ETF（否则估值会变成 0）。"""
    code = fund["code"]
    name = str(fund.get("name") or fund.get("label") or "")
    stocks = parse_f10_stock_holdings(code) or []
    stock_sum = sum(h[3] for h in stocks)
    feeder = fund.get("feeder_etf")
    # 非内置联接：股票仓往往只有几个点，「其他」才是目标 ETF
    if not feeder and ("联接" in name or stock_sum < 40.0):
        try:
            feeder = detect_feeder_etf(code, name)
        except Exception:
            feeder = None
        if feeder:
            fund["feeder_etf"] = feeder  # 缓存到 fund dict，后续刷新可复用

    if feeder:
        market, etf_code, etf_w = feeder
        stock_part = [h for h in stocks if h[1] != etf_code]
        # 内置模板：若 F10 股票异常偏高/失败，回退内置股票部分
        builtin = list(fund.get("holdings") or [])
        if builtin and (not stocks or sum(h[3] for h in stock_part) > 30):
            stock_part = [h for h in builtin if h[1] != etf_code]
        return [(market, etf_code, "目标ETF", float(etf_w))] + stock_part

    builtin = list(fund.get("holdings") or [])
    if stocks:
        # F10 常只给前十大，覆盖度明显低于内置全成分时，保留内置（否则估值漂移）
        stock_cov = sum(h[3] for h in stocks)
        builtin_cov = sum(h[3] for h in builtin)
        if builtin and builtin_cov > stock_cov + 5.0:
            return builtin
        return stocks
    return builtin


def holdings_to_sina_codes(holdings: List[Holding]) -> List[str]:
    codes = []
    for market, code, _n, _w in holdings:
        if market == "hk":
            codes.append(f"rt_hk{code}")
        else:
            codes.append(f"{market}{code}")
    return codes


# ---------- 当日分时（东财 trends2）----------
def _em_secid(market: str, code: str) -> Optional[str]:
    m = (market or "").strip().lower()
    c = (code or "").strip()
    if not c:
        return None
    if m == "hk" or c.upper() == "HSTECH":
        if c.upper() == "HSTECH":
            return "124.HSTECH"
        digits = re.sub(r"\D", "", c).zfill(5)
        return f"116.{digits}"
    if m in ("sh", "sz"):
        digits = re.sub(r"\D", "", c).zfill(6)[-6:]
        return ("1." if m == "sh" else "0.") + digits
    return None


def _secid_from_sina_key(key: str) -> Optional[str]:
    k = (key or "").strip()
    if not k:
        return None
    if "HSTECH" in k.upper():
        return "124.HSTECH"
    if k.startswith("rt_hk"):
        return _em_secid("hk", k[5:])
    if k.startswith("s_sh"):
        return _em_secid("sh", k[4:])
    if k.startswith("s_sz"):
        return _em_secid("sz", k[4:])
    if k.startswith("sh"):
        return _em_secid("sh", k[2:])
    if k.startswith("sz"):
        return _em_secid("sz", k[2:])
    return None


def _iter_session_minutes(start: dtime, end: dtime) -> List[str]:
    t = datetime(2000, 1, 1, start.hour, start.minute)
    last = datetime(2000, 1, 1, end.hour, end.minute)
    out: List[str] = []
    while t <= last:
        out.append(t.strftime("%H:%M"))
        t += timedelta(minutes=1)
    return out


SESSION_AXES: Dict[str, List[str]] = {
    "cn": _iter_session_minutes(dtime(9, 30), dtime(11, 30))
    + _iter_session_minutes(dtime(13, 0), dtime(15, 0)),
    "hk": _iter_session_minutes(dtime(9, 30), dtime(12, 0))
    + _iter_session_minutes(dtime(13, 0), dtime(16, 0)),
    "mix": _iter_session_minutes(dtime(9, 30), dtime(12, 0))
    + _iter_session_minutes(dtime(13, 0), dtime(16, 0)),
}


_trend_cache: Dict[str, Tuple[float, str, Optional[dict]]] = {}
_trend_cache_lock = threading.Lock()
_trend_inflight: Dict[str, "_TrendWait"] = {}
_TREND_OK_TTL = 45.0
_TREND_FAIL_TTL = 2.0
_FUND_CURVE_MIN_COVER = 0.75


class _TrendWait:
    def __init__(self) -> None:
        self.event = threading.Event()
        self.value: Optional[dict] = None


def _invalidate_trend_cache() -> None:
    with _trend_cache_lock:
        _trend_cache.clear()


def _curve_cap_hm(trends: Dict[str, dict]) -> str:
    """曲线只画到「现在」与最新分时之间的较早者，避免盘中把线拉平到收盘。"""
    cap = now_shanghai().strftime("%H:%M")
    last = None
    for tr in (trends or {}).values():
        pts = (tr or {}).get("points") or []
        if pts:
            hm = pts[-1][0]
            if last is None or hm > last:
                last = hm
    if last:
        cap = min(cap, last)
    return cap


def _clip_curve(
    points: List[Tuple[str, Optional[float]]], cap_hm: str
) -> List[Tuple[str, Optional[float]]]:
    return [(t, v if t <= cap_hm else None) for t, v in points]


def _tencent_code_from_secid(secid: str) -> Optional[str]:
    s = (secid or "").strip()
    if "." not in s:
        return None
    market, code = s.split(".", 1)
    code = (code or "").strip()
    if market == "1" and code:
        return "sh" + code
    if market == "0" and code:
        return "sz" + code
    if market in ("116", "124") and code:
        return "hk" + code
    return None


def _qt_row(qt: dict, code: str) -> list:
    row = qt.get(code)
    if isinstance(row, list) and len(row) >= 5:
        return row
    for v in qt.values():
        if isinstance(v, list) and len(v) >= 5:
            return v
    return []


def _parse_hm_token(token: str) -> Optional[str]:
    t = (token or "").strip()
    if len(t) == 4 and t.isdigit():
        return t[:2] + ":" + t[2:]
    if len(t) >= 5 and t[2] == ":":
        return t[:5]
    return None


def _fetch_tencent_trend(secid: str) -> Optional[dict]:
    """腾讯分时。用户电脑上东财 push2 经常被掐断，这条更稳。"""
    code = _tencent_code_from_secid(secid)
    if not code:
        return None
    url = "https://web.ifzq.gtimg.cn/appstock/app/minute/query?code=" + code
    text = _http_get(url, extra_headers={"Referer": "https://gu.qq.com/"})
    js = json.loads(text) if text else {}
    if (js or {}).get("code") not in (0, "0"):
        return None
    payload = ((js or {}).get("data") or {}).get(code) or {}
    if not isinstance(payload, dict):
        return None
    inner = payload.get("data") or {}
    if not isinstance(inner, dict):
        return None
    day = str(inner.get("date") or "").replace("-", "")
    today_compact = _trade_date_str().replace("-", "")
    if day != today_compact:
        return None
    qt = payload.get("qt") or {}
    if not isinstance(qt, dict):
        return None
    row = _qt_row(qt, code)
    if len(row) < 5:
        return None
    got = str(row[2] or "").upper()
    want = code[2:].upper() if code[:2].lower() in ("sh", "sz", "hk") else code.upper()
    if got and want and got != want:
        return None
    try:
        pre = float(row[4])
    except Exception:
        return None
    if pre <= 0:
        return None
    points: List[Tuple[str, float]] = []
    for raw in inner.get("data") or []:
        try:
            parts = str(raw).split()
            if len(parts) < 2:
                continue
            hm = _parse_hm_token(parts[0])
            if not hm:
                continue
            price = float(parts[1])
            if price <= 0:
                continue
            points.append((hm, price))
        except Exception:
            continue
    if not points:
        return None
    return {
        "secid": secid,
        "name": str(row[1] or ""),
        "pre": pre,
        "points": points,
        "date": _trade_date_str(),
        "source": "tencent",
    }


def _fetch_eastmoney_trend(secid: str) -> Optional[dict]:
    """东财 trends2 兜底。校验 secid / 当日日期 / preClose，错日或错品种直接丢弃。"""
    url = (
        "https://push2.eastmoney.com/api/qt/stock/trends2/get"
        f"?secid={secid}&fields1=f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13"
        "&fields2=f51,f52,f53,f54,f55,f56,f57,f58&ndays=1&iscr=0"
    )
    text = _http_get(url, extra_headers={"Referer": "https://quote.eastmoney.com/"})
    data = (json.loads(text) or {}).get("data") or {} if text else {}
    if not data:
        return None
    got_code = str(data.get("code") or "").upper()
    got_mkt = str(data.get("market") or "")
    want_mkt, _, want_code = secid.partition(".")
    if got_code != want_code.upper() or got_mkt != want_mkt:
        return None
    try:
        pre = float(data.get("preClose") or data.get("prePrice") or 0)
    except Exception:
        pre = 0.0
    if pre <= 0:
        return None
    today = _trade_date_str()
    points: List[Tuple[str, float]] = []
    for raw in data.get("trends") or []:
        try:
            head, *rest = str(raw).split(",")
            parts = head.strip().split(" ", 1)
            if len(parts) != 2 or len(rest) < 2:
                continue
            day, hm = parts
            if day != today:
                continue
            hm = hm[:5]
            price = float(rest[1])
            if price <= 0:
                continue
            points.append((hm, price))
        except Exception:
            continue
    if not points:
        return None
    return {
        "secid": secid,
        "name": str(data.get("name") or ""),
        "pre": pre,
        "points": points,
        "date": today,
        "source": "eastmoney",
    }


def _fetch_minute_trend_uncached(secid: str) -> Optional[dict]:
    for fn in (_fetch_tencent_trend, _fetch_eastmoney_trend):
        try:
            out = fn(secid)
        except Exception:
            out = None
        if out and out.get("points") and float(out.get("pre") or 0) > 0:
            return out
    return None


def fetch_minute_trend(secid: str) -> Optional[dict]:
    """分时。返回 {name, pre, points: [(HH:MM, price), ...]}；失败不长期缓存。"""
    if not secid:
        return None
    now_ts = time.time()
    today = _trade_date_str()
    with _trend_cache_lock:
        hit = _trend_cache.get(secid)
        if hit and hit[1] == today:
            ts, _day, val = hit
            ttl = _TREND_OK_TTL if val else _TREND_FAIL_TTL
            if now_ts - ts < ttl:
                return val
        waiter = _trend_inflight.get(secid)
        mine = False
        if waiter is None:
            waiter = _TrendWait()
            _trend_inflight[secid] = waiter
            mine = True
    if not mine:
        waiter.event.wait(25)
        return waiter.value
    try:
        out = _fetch_minute_trend_uncached(secid)
        waiter.value = out
        with _trend_cache_lock:
            _trend_cache[secid] = (time.time(), today, out)
        return out
    finally:
        waiter.event.set()
        with _trend_cache_lock:
            if _trend_inflight.get(secid) is waiter:
                del _trend_inflight[secid]


def fetch_minute_trends(secids: List[str]) -> Dict[str, dict]:
    uniq: List[str] = []
    seen = set()
    for s in secids:
        if s and s not in seen:
            seen.add(s)
            uniq.append(s)
    out: Dict[str, dict] = {}
    if not uniq:
        return out
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(fetch_minute_trend, s): s for s in uniq}
        for fut in as_completed(futs):
            s = futs[fut]
            try:
                tr = fut.result()
            except Exception:
                tr = None
            if tr and tr.get("points") and float(tr.get("pre") or 0) > 0:
                out[s] = tr
    return out


def _pct_points(trend: dict) -> List[Tuple[str, float]]:
    try:
        pre = float(trend.get("pre") or 0)
    except Exception:
        pre = 0.0
    if pre <= 0:
        return []
    return [(hm, (px / pre - 1.0) * 100.0) for hm, px in (trend.get("points") or [])]


def _lookup_last(series: List[Tuple[str, float]], hm: str) -> Optional[float]:
    last: Optional[float] = None
    for t, v in series:
        if t <= hm:
            last = v
        else:
            break
    return last


def _align_pct(trend: dict, axis: List[str]) -> List[Tuple[str, Optional[float]]]:
    pts = _pct_points(trend)
    return [(hm, _lookup_last(pts, hm)) for hm in axis]


def _curve_has_values(points: List[Tuple[str, Optional[float]]]) -> bool:
    return any(v is not None for _, v in (points or []))


def _session_hm_now(axis_kind: str = "mix") -> str:
    """当前时刻落在该交易轴上的最后一个时间格（未开盘则为轴首）。"""
    now = now_shanghai().strftime("%H:%M")
    axis = SESSION_AXES.get(axis_kind) or SESSION_AXES["mix"]
    last = axis[0] if axis else now
    for t in axis:
        if t <= now:
            last = t
        else:
            break
    return last


def _anchor_curve_last(
    points: List[Tuple[str, Optional[float]]],
    live: Optional[float],
    hm: str,
) -> List[Tuple[str, Optional[float]]]:
    """把可见末点改成与主浮窗相同的实时估值，标题「现」随之对齐。"""
    if live is None or not points:
        return points
    out = list(points)
    idx = None
    for i, (t, _v) in enumerate(out):
        if t <= hm:
            idx = i
        else:
            break
    if idx is None:
        return out
    t, _ = out[idx]
    out[idx] = (t, float(live))
    return out


def book_from_snap(items: List[dict], snap: Optional[dict]) -> dict:
    """与主浮窗合计同一口径：全持仓估值 × 本金。"""
    snap = snap or {}
    funds = snap.get("funds") or {}
    stocks = snap.get("stocks") or {}
    fund_pct: Dict[str, float] = {}
    stock_pct: Dict[str, float] = {}
    total_pnl = 0.0
    has_total = False
    for it in items or []:
        code = str(it.get("code") or "")
        try:
            amt = float(it.get("amount") or 0.0)
        except Exception:
            amt = 0.0
        if it.get("kind") == "stock":
            ss = stocks.get(code) or {}
            if "pct" not in ss:
                continue
            try:
                pct = float(ss.get("pct") or 0.0)
            except Exception:
                continue
            stock_pct[code] = pct
            if amt > 0:
                total_pnl += amt * pct / 100.0
                has_total = True
        else:
            fs = funds.get(code) or {}
            if "est_pct" not in fs:
                continue
            try:
                pct = float(fs.get("est_pct") or 0.0)
            except Exception:
                continue
            fund_pct[code] = pct
            if amt > 0:
                total_pnl += amt * pct / 100.0
                has_total = True
    sh_pct = hk_pct = None
    try:
        sh_pct = float(snap["sh"][2])  # type: ignore[index]
    except Exception:
        sh_pct = None
    try:
        hk_pct = float(snap["hstech"][2])  # type: ignore[index]
    except Exception:
        hk_pct = None
    return {
        "total_pnl": total_pnl if has_total else None,
        "fund_pct": fund_pct,
        "stock_pct": stock_pct,
        "sh_pct": sh_pct,
        "hstech_pct": hk_pct,
    }


def live_map_from_book(book: dict) -> Dict[str, float]:
    out: Dict[str, float] = {}
    if not book:
        return out
    if book.get("total_pnl") is not None:
        out["total"] = float(book["total_pnl"])
    if book.get("sh_pct") is not None:
        out["sh"] = float(book["sh_pct"])
    if book.get("hstech_pct") is not None:
        out["hstech"] = float(book["hstech_pct"])
    for code, pct in (book.get("fund_pct") or {}).items():
        out[f"fund:{code}"] = float(pct)
    for code, pct in (book.get("stock_pct") or {}).items():
        out[f"stock:{code}"] = float(pct)
    return out


def apply_live_to_tabs(tabs: List[dict], live_map: Dict[str, float]) -> List[dict]:
    if not tabs or not live_map:
        return tabs
    now_by = {
        "cn": _session_hm_now("cn"),
        "hk": _session_hm_now("hk"),
        "mix": _session_hm_now("mix"),
    }
    out = []
    for tab in tabs:
        t = dict(tab)
        key = t.get("key")
        if key in live_map and _curve_has_values(t.get("points") or []):
            kind = t.get("axis") or "cn"
            t["points"] = _anchor_curve_last(
                list(t.get("points") or []),
                live_map[key],
                now_by.get(kind) or _session_hm_now(kind),
            )
        out.append(t)
    return out


def _fund_curve(
    holdings: List[Holding],
    trends: Dict[str, dict],
    axis: List[str],
) -> List[Tuple[str, Optional[float]]]:
    series: List[List[Tuple[str, float]]] = []
    weights: List[float] = []
    total_w = 0.0
    used_w = 0.0
    for market, code, _n, w in holdings:
        try:
            wf = float(w)
        except Exception:
            continue
        if wf <= 0:
            continue
        total_w += wf
        sid = _em_secid(market, code)
        if not sid:
            continue
        tr = trends.get(sid)
        if not tr:
            continue
        pts = _pct_points(tr)
        if not pts:
            continue
        series.append(pts)
        weights.append(wf)
        used_w += wf
    if total_w <= 0 or used_w / total_w < _FUND_CURVE_MIN_COVER:
        return [(hm, None) for hm in axis]
    out: List[Tuple[str, Optional[float]]] = []
    for hm in axis:
        est = 0.0
        used = 0
        for pts, w in zip(series, weights):
            pct = _lookup_last(pts, hm)
            if pct is None:
                continue
            est += w * pct / 100.0
            used += 1
        out.append((hm, est if used else None))
    return out


def _total_pnl_curve(
    items: List[dict],
    fund_curves: Dict[str, List[Tuple[str, Optional[float]]]],
    stock_curves: Dict[str, List[Tuple[str, Optional[float]]]],
    axis: List[str],
) -> List[Tuple[str, Optional[float]]]:
    # 任一有金额的品种曲线缺失时，宁可不画合计，避免残缺加权画出错误盈亏。
    for it in items:
        try:
            amt = float(it.get("amount") or 0)
        except Exception:
            amt = 0.0
        if amt == 0:
            continue
        code = it.get("code") or ""
        cur = (stock_curves if it.get("kind") == "stock" else fund_curves).get(code) or []
        if not _curve_has_values(cur):
            return [(hm, None) for hm in axis]
    out: List[Tuple[str, Optional[float]]] = []
    for i, hm in enumerate(axis):
        total = 0.0
        used = 0
        for it in items:
            try:
                amt = float(it.get("amount") or 0)
            except Exception:
                amt = 0.0
            if amt == 0:
                continue
            code = it.get("code") or ""
            cur = (stock_curves if it.get("kind") == "stock" else fund_curves).get(code) or []
            pct = cur[i][1] if i < len(cur) else None
            if pct is None:
                continue
            total += amt * float(pct) / 100.0
            used += 1
        out.append((hm, total if used else None))
    return out


def estimate_fund(
    holdings: List[Holding],
    batch: Dict[str, List[str]],
    prev_nav: Optional[float],
) -> Tuple[float, Optional[float], int, float, Optional[dict], Optional[dict]]:
    """返回 est_pct, est_nav, used, covered, drag, boost。
    contrib（基金百分点）= (weight%/100) × 个股涨跌% = weight × chg / 100。
    drag=贡献最低（最拖累）；boost=贡献最高。
    """
    est = 0.0
    used = 0
    covered = 0.0
    drag: Optional[dict] = None
    boost: Optional[dict] = None
    for market, code, name, weight in holdings:
        if weight <= 0:
            continue
        key = f"rt_hk{code}" if market == "hk" else f"{market}{code}"
        fields = batch.get(key)
        if not fields:
            continue
        try:
            if market == "hk":
                _p, _c, pct = _pct_from_hk(fields)
            else:
                _p, _c, pct = _pct_from_a(fields)
        except Exception:
            continue
        contrib = weight * pct / 100.0
        est += contrib
        used += 1
        covered += weight
        item = {
            "name": str(name or code),
            "code": str(code),
            "market": market,
            "weight": float(weight),
            "pct": float(pct),
            "contrib": float(contrib),
        }
        if drag is None or contrib < float(drag["contrib"]):
            drag = item
        if boost is None or contrib > float(boost["contrib"]):
            boost = item
    est_nav = prev_nav * (1.0 + est / 100.0) if prev_nav else None
    return est, est_nav, used, covered, drag, boost


def fmt_contrib_cell(item: Optional[dict]) -> Tuple[str, float]:
    """紧凑：两字简称 + 对基金贡献百分点。如 金山-0.1%。"""
    if not item:
        return "", 0.0
    name = _short_cn(str(item.get("name") or item.get("code") or "?"), 2)
    c = float(item.get("contrib") or 0.0)
    sign = "+" if c > 0 else ""
    return f"{name}{sign}{c:.1f}%", c


def holding_contrib_rows(
    holdings: List[Holding], batch: Dict[str, List[str]]
) -> List[dict]:
    """每只持仓：权重%、涨跌%、贡献=(weight/100)*chg%。按贡献升序（最拖累在上）。"""
    rows: List[dict] = []
    for market, code, name, weight in holdings:
        if weight <= 0:
            continue
        key = f"rt_hk{code}" if market == "hk" else f"{market}{code}"
        fields = batch.get(key)
        pct: Optional[float] = None
        if fields:
            try:
                if market == "hk":
                    _p, _c, pct = _pct_from_hk(fields)
                else:
                    _p, _c, pct = _pct_from_a(fields)
            except Exception:
                pct = None
        if pct is None:
            continue
        w = float(weight)
        contrib = w * float(pct) / 100.0
        rows.append(
            {
                "name": str(name or code),
                "code": str(code),
                "market": market,
                "weight": w,
                "pct": float(pct),
                "contrib": contrib,
            }
        )
    rows.sort(key=lambda r: r["contrib"])
    return rows



# ---------- 自选持仓配置（holdings.json）----------
CONFIG_PATH = Path(__file__).resolve().parent / "holdings.json"
EST_LOG_PATH = Path(__file__).resolve().parent / "estimates_log.csv"
EST_LOG_FIELDS = [
    "date", "code", "label", "est_pct", "est_nav", "prev_nav", "nav_date",
    "covered", "used", "snap_time",
    "official_nav", "official_pct", "official_date",
    "err_pct", "err_nav", "filled_at",
]

# 内置基金模板（按 code 匹配；未知基金走 F10 动态持仓）
BUILTIN_BY_CODE = {f["code"]: f for f in FUNDS}

DEFAULT_ITEMS = [
    {"code": "017435", "kind": "fund", "label": "港股消费", "amount": 38000.0},
    {"code": "161725", "kind": "fund", "label": "白酒", "amount": 8000.0},
    {"code": "011612", "kind": "fund", "label": "科创50", "amount": 4000.0},
]


def _short_cn(name: str, n: int = 4) -> str:
    """从全称压成短标签。"""
    if not name:
        return ""
    s = name.strip()
    for junk in (
        "ETF联接", "联接基金", "交易型开放式指数", "指数证券投资基金",
        "证券投资基金", "开放式", "指数基金", "股票基金", "混合基金",
        "(LOF)", "（LOF）", "LOF", "ETF", "联接", "指数",
    ):
        s = s.replace(junk, "")
    for ch in "AaBbCc":
        if s.endswith(ch) and len(s) > 1:
            s = s[:-1]
    s = s.strip("-_ ·")
    # 取前 n 个非空字符（中文按字）
    out = []
    for ch in s:
        if ch.isspace():
            continue
        out.append(ch)
        if len(out) >= n:
            break
    return "".join(out) or name[:n]


def fetch_fund_name(code: str) -> Optional[str]:
    try:
        url = (
            "https://fundsuggest.eastmoney.com/FundSearch/api/FundSearchAPI.ashx"
            f"?m=1&key={code}"
        )
        text = _http_get(url, extra_headers={"Referer": "https://fund.eastmoney.com/"})
        data = json.loads(text).get("Datas") or []
        for row in data:
            if str(row.get("CODE") or "") == code:
                return str(row.get("NAME") or "") or None
        if data:
            return str(data[0].get("NAME") or "") or None
    except Exception:
        return None
    return None


def sina_keys_for_stock(code: str) -> List[str]:
    """猜测 A 股/港股 sina list key。"""
    c = code.strip().upper()
    if c.startswith("HK"):
        return [f"rt_hk{c[2:].zfill(5)}"]
    if c.startswith(("SH", "SZ")):
        return [c.lower()]
    digits = re.sub(r"\D", "", c)
    if len(digits) == 5:
        return [f"rt_hk{digits.zfill(5)}"]
    digits = digits.zfill(6)[-6:]
    if digits.startswith(("5", "6", "9")):
        return [f"sh{digits}"]
    if digits.startswith(("0", "1", "2", "3")):
        return [f"sz{digits}"]
    return [f"sh{digits}", f"sz{digits}"]


def probe_stock_quote(code: str) -> Optional[Tuple[str, str, float, float, float]]:
    """返回 (sina_key, name, price, change, pct) 或 None。"""
    keys = sina_keys_for_stock(code)
    batch = _sina_batch(keys)
    for key in keys:
        fields = batch.get(key)
        if not fields:
            continue
        try:
            if key.startswith("rt_hk"):
                name = fields[0]
                price, change, pct = _pct_from_hk(fields)
            else:
                name = fields[0]
                price, change, pct = _pct_from_a(fields)
            if price <= 0:
                continue
            return key, name, price, change, pct
        except Exception:
            continue
    return None


def resolve_instrument(code: str) -> dict:
    """
    根据代码判定 fund/stock，并给出短标签。
    返回 {code, kind, label, name?, sina_key?}

    规则概要：
    - 显式 sh/sz/hk 前缀 → 行情（stock）
    - 内置三只基金模板 → fund
    - 60/68/30/5 开头 → 优先 A 股/ETF 行情（避免基金搜索误伤）
    - 其余 6 位：东财净值能取到 → fund，否则行情
    """
    raw = code.strip().upper()
    digits = re.sub(r"\D", "", raw)
    if raw.startswith(("SH", "SZ")) and len(digits) == 6:
        hit = probe_stock_quote(raw)
        if not hit:
            raise ValueError(f"找不到行情: {code}")
        key, name, *_ = hit
        label = _short_cn(name, 4) or digits
        return {"code": digits, "kind": "stock", "label": label, "name": name, "sina_key": key}
    if raw.startswith("HK") or len(digits) == 5:
        dig = digits.zfill(5)
        hit = probe_stock_quote("HK" + dig)
        if not hit:
            raise ValueError(f"找不到港股: {code}")
        key, name, *_ = hit
        return {"code": dig, "kind": "stock", "label": _short_cn(name, 4) or dig, "name": name, "sina_key": key}

    code6 = digits.zfill(6)[-6:]
    if code6 in BUILTIN_BY_CODE:
        b = BUILTIN_BY_CODE[code6]
        return {
            "code": code6,
            "kind": "fund",
            "label": b["label"],
            "name": b["name"],
        }

    # 明显的上市股票 / ETF 代码 → 行情
    if code6.startswith(("60", "68", "30", "5")):
        hit = probe_stock_quote(code6)
        if hit:
            key, name, *_ = hit
            return {
                "code": code6,
                "kind": "stock",
                "label": _short_cn(name, 4) or code6,
                "name": name,
                "sina_key": key,
            }

    # 净值接口比「搜索联想」更可靠（搜索会把股票名也搜出来）
    try:
        fetch_fund_nav(code6)
        is_fund = True
    except Exception:
        is_fund = False
    if is_fund:
        fname = fetch_fund_name(code6) or code6
        return {
            "code": code6,
            "kind": "fund",
            "label": _short_cn(fname, 4) or code6,
            "name": fname,
        }

    hit = probe_stock_quote(code6)
    if hit:
        key, name, *_ = hit
        return {
            "code": code6,
            "kind": "stock",
            "label": _short_cn(name, 4) or code6,
            "name": name,
            "sina_key": key,
        }
    raise ValueError(f"无法识别代码: {code}")


def _normalize_item(it: dict) -> Optional[dict]:
    if not isinstance(it, dict):
        return None
    code = str(it.get("code") or "").strip()
    if not code:
        return None
    kind = str(it.get("kind") or "fund").lower()
    if kind not in ("fund", "stock"):
        kind = "fund"
    label = str(it.get("label") or code).strip() or code
    try:
        amount = float(it.get("amount") or 0.0)
    except Exception:
        amount = 0.0
    if amount < 0:
        amount = 0.0
    out = {"code": code, "kind": kind, "label": label, "amount": amount}
    if it.get("sina_key"):
        out["sina_key"] = str(it["sina_key"])
    if it.get("name"):
        out["name"] = str(it["name"])
    return out


def load_items() -> List[dict]:
    """读取自选列表；兼容旧版 {code: amount}。"""
    try:
        if not CONFIG_PATH.exists():
            items = [dict(x) for x in DEFAULT_ITEMS]
            save_items(items)
            return items
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        if isinstance(raw, dict) and isinstance(raw.get("items"), list):
            items = []
            for it in raw["items"]:
                n = _normalize_item(it)
                if n:
                    items.append(n)
            return items or [dict(x) for x in DEFAULT_ITEMS]
        # 旧格式：{"017435": 38000, ...}
        if isinstance(raw, dict):
            items = []
            # 保持默认顺序，再追加未知 code
            seen = set()
            for d in DEFAULT_ITEMS:
                code = d["code"]
                if code in raw:
                    items.append({
                        "code": code,
                        "kind": "fund",
                        "label": d["label"],
                        "amount": float(raw[code]),
                    })
                    seen.add(code)
            for code, amt in raw.items():
                if code in seen or code in ("version", "items"):
                    continue
                try:
                    a = float(amt)
                except Exception:
                    continue
                label = BUILTIN_BY_CODE.get(code, {}).get("label") or code
                items.append({"code": str(code), "kind": "fund", "label": label, "amount": a})
            if items:
                return items
    except Exception:
        pass
    return [dict(x) for x in DEFAULT_ITEMS]


def save_items(items: List[dict]) -> None:
    clean = []
    for it in items:
        n = _normalize_item(it)
        if n:
            clean.append(n)
    payload = {"version": 2, "items": clean}
    CONFIG_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def fund_dict_for(item: dict) -> dict:
    """构造 refresh_fund_holdings / estimate 用的 fund dict。"""
    code = item["code"]
    b = BUILTIN_BY_CODE.get(code)
    if b:
        return {
            "code": code,
            "label": item.get("label") or b["label"],
            "name": b["name"],
            "holdings": list(b["holdings"]),
            "feeder_etf": b.get("feeder_etf"),
        }
    return {
        "code": code,
        "label": item.get("label") or code,
        "name": item.get("name") or item.get("label") or code,
        "holdings": [],
        "feeder_etf": None,
    }


class FloatWidget:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("盯盘")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        try:
            self.root.attributes("-alpha", ALPHA)
        except tk.TclError:
            pass

        self.bg = "#1a1a1a"
        self.fg = "#9a9a9a"
        self.fg_up = "#8f5a5a"  # A-share: red = up/profit
        self.fg_dn = "#5a8f6a"  # A-share: green = down/loss
        self.fg_flat = "#8a8a8a"
        self.root.configure(bg=self.bg)

        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = sw - WIN_W - MARGIN
        y = sh - WIN_H - MARGIN - 40
        self.root.geometry(f"{WIN_W}x{WIN_H}+{x}+{y}")

        self.font = ("Segoe UI", 9)
        self.font_mono = ("Consolas", 9)
        self._items: List[dict] = load_items()

        self.rows: List[dict] = []
        self._pad: Optional[tk.Frame] = None
        self._build_row("上证", kind="index", key="sh")
        self._build_row("恒科", kind="index", key="hstech")
        for it in self._items:
            kind = it.get("kind") or "fund"
            self._build_row(it["label"], kind=kind, key=it["code"])
        self._build_row("合计", kind="total", key="total")
        self._pad = tk.Frame(self.root, height=5, bg=self.bg)
        self._pad.pack(fill="x")

        # 折叠条：只显示合计当日盈亏（不 pack，展开时隐藏）
        self._mini = tk.Label(
            self.root,
            text="—",
            font=self.font_mono,
            fg=self.fg,
            bg=self.bg,
            anchor="center",
            padx=6,
            pady=1,
        )
        self._mini_pnl_text = "—"
        self._mini_pnl_fg = self.fg

        self._drag_x = 0
        self._drag_y = 0
        self._hidden = False
        self._toggling = False
        self._last_toggle_ts = 0.0
        self._lock = threading.Lock()
        self._stop = False
        self._err_streak = 0
        self._fund_state: Dict[str, dict] = {}
        self._stock_keys: Dict[str, str] = {}  # code -> sina key
        self._init_states_from_items()
        self._snap: Dict[str, object] = {}

        self._bind_all()
        self.menu = Menu(self.root, tearoff=0)
        self.menu.add_command(label="刷新", command=self._force_refresh)
        self.menu.add_command(label="看详细…", command=self._show_fund_detail)
        self.menu.add_command(label="今日曲线…", command=self._show_today_curve)
        self.menu.add_command(label="设置持仓…", command=self._edit_amounts)
        self._curve_win = None
        self.menu.add_command(label="估值误差…", command=self._show_est_errors)
        self.menu.add_command(label="打开日志目录", command=self._open_log_dir)
        self.menu.add_command(label="置顶切换", command=self._toggle_topmost)
        self.menu.add_separator()
        self.menu.add_command(label="退出", command=self.quit)

        threading.Thread(target=self._bootstrap, daemon=True).start()
        threading.Thread(target=self._poll_loop, daemon=True).start()

    def _init_states_from_items(self) -> None:
        self._fund_state = {}
        self._stock_keys = {}
        for it in self._items:
            code = it["code"]
            if it.get("kind") == "stock":
                sk = it.get("sina_key")
                if not sk:
                    keys = sina_keys_for_stock(code)
                    sk = keys[0] if keys else ""
                self._stock_keys[code] = sk
            else:
                fd = fund_dict_for(it)
                self._fund_state[code] = {
                    "holdings": list(fd["holdings"]),
                    "prev_nav": None,
                    "nav_date": "",
                    "fund": fd,
                }

    # 浮窗列：标签 | 拖累贡献 | 最大贡献 | 估值%/价 | 收 | 盈亏
    LABEL_MAX = 4
    COL_LABEL = 8
    COL_DRAG = 9
    COL_BOOST = 9
    COL_PCT = 7
    COL_MARK = 1
    COL_PNL = 5

    def _build_row(self, title: str, *, kind: str, key: str) -> None:
        fr = tk.Frame(self.root, bg=self.bg)
        if self._pad is not None:
            fr.pack(fill="x", padx=4, pady=(3 if not self.rows else 0, 0), before=self._pad)
        else:
            fr.pack(fill="x", padx=4, pady=(3 if not self.rows else 0, 0))
        lab = tk.Label(
            fr,
            text=title[: self.LABEL_MAX],
            font=self.font,
            fg=self.fg,
            bg=self.bg,
            anchor="w",
            width=self.COL_LABEL,
        )
        # 基金：最拖累；指数/股票：价格
        drag = tk.Label(
            fr,
            text="",
            font=self.font,
            fg=self.fg,
            bg=self.bg,
            anchor="e",
            width=self.COL_DRAG,
        )
        # 基金：贡献最大；其它行留空
        boost = tk.Label(
            fr,
            text="",
            font=self.font,
            fg=self.fg,
            bg=self.bg,
            anchor="e",
            width=self.COL_BOOST,
        )
        pct = tk.Label(
            fr,
            text="…",
            font=self.font_mono,
            fg=self.fg,
            bg=self.bg,
            anchor="e",
            width=self.COL_PCT,
        )
        mark = tk.Label(
            fr,
            text="",
            font=self.font,
            fg=self.fg,
            bg=self.bg,
            anchor="center",
            width=self.COL_MARK,
        )
        pnl = tk.Label(
            fr,
            text="—",
            font=self.font_mono,
            fg=self.fg,
            bg=self.bg,
            anchor="e",
            width=self.COL_PNL,
        )
        lab.pack(side="left")
        drag.pack(side="left", padx=(4, 0))
        boost.pack(side="left", padx=(2, 0))
        pct.pack(side="left", padx=(2, 0))
        mark.pack(side="left", padx=(2, 0))
        pnl.pack(side="left", padx=(4, 0))
        self.rows.append(
            {
                "frame": fr,
                "lab": lab,
                "drag": drag,
                "boost": boost,
                "price": drag,  # 兼容：指数/股票把价格画在 drag 列
                "pct": pct,
                "mark": mark,
                "pnl": pnl,
                "left": lab,
                "right": pnl,
                "kind": kind,
                "key": key,
                "title": title,
            }
        )

    def _rebuild_watch_rows(self) -> None:
        """按 self._items 重建中间自选行（保留 上证/恒科/合计）。"""
        index_rows = []
        total_row = None
        for r in self.rows:
            if r["kind"] == "index":
                index_rows.append(r)
            elif r["kind"] == "total":
                total_row = r
            else:
                r["frame"].destroy()
        # 全部 unpack 后按固定顺序重排
        for r in index_rows:
            r["frame"].pack_forget()
        if total_row is not None:
            total_row["frame"].pack_forget()
        if self._pad is not None:
            self._pad.pack_forget()

        self.rows = []
        for r in index_rows:
            r["frame"].pack(fill="x", padx=5, pady=(4 if not self.rows else 0, 0))
            self.rows.append(r)
        self._pad = None  # temporarily so _build_row appends normally
        for it in self._items:
            kind = it.get("kind") or "fund"
            self._build_row(it["label"], kind=kind, key=it["code"])
        if total_row is not None:
            total_row["frame"].pack(fill="x", padx=5, pady=0)
            self.rows.append(total_row)
        self._pad = tk.Frame(self.root, height=5, bg=self.bg)
        self._pad.pack(fill="x")
        self._bind_all()
        if self._hidden:
            self._show_mini_only()

    def _bind_all(self) -> None:
        # 注意：Tk bindtags 含 toplevel，子控件事件也会落到 root。
        # Double-Button 只绑 root 一次，否则会 toggle 两次（折叠立刻又展开=闪一下）。
        widgets = [self.root, self._mini]
        for r in self.rows:
            widgets.extend(
                [
                    r["frame"],
                    r["lab"],
                    r["drag"],
                    r["boost"],
                    r["pct"],
                    r["mark"],
                    r["pnl"],
                ]
            )
        for w in widgets:
            w.bind("<ButtonPress-1>", self._on_press)
            w.bind("<B1-Motion>", self._on_drag)
            w.bind("<Button-3>", self._popup)
            # 清掉可能残留的双击绑定（热重建行时）
            w.unbind("<Double-Button-1>")
        self.root.bind("<Double-Button-1>", self._toggle_thin)

    def _bootstrap(self) -> None:
        self._refresh_fund_meta()
        self._one_fetch()

    def _refresh_fund_meta(self) -> None:
        """拉取基金持仓明细与净值（仅 fund 行）。"""
        with self._lock:
            codes = list(self._fund_state.keys())
            funds = {
                c: dict(
                    self._fund_state[c].get("fund")
                    or fund_dict_for({"code": c, "kind": "fund", "label": c})
                )
                for c in codes
            }
        for code, fd in funds.items():
            # 补全全称，便于联接基金识别目标 ETF
            if not fd.get("name") or fd.get("name") == code or fd.get("name") == fd.get("label"):
                try:
                    nm = fetch_fund_name(code)
                    if nm:
                        fd["name"] = nm
                except Exception:
                    pass
            try:
                holdings = refresh_fund_holdings(fd)
            except Exception:
                holdings = list(fd.get("holdings") or [])
            try:
                nav, day = fetch_prev_nav_for_estimate(code)
            except Exception:
                nav, day = None, ""
            with self._lock:
                if code in self._fund_state:
                    self._fund_state[code]["holdings"] = holdings
                    self._fund_state[code]["prev_nav"] = nav
                    self._fund_state[code]["nav_date"] = day
                    self._fund_state[code]["fund"] = fd

    def _virtual_screen(self) -> Tuple[int, int, int, int]:
        """虚拟桌面 (vx, vy, vw, vh)；失败则主屏。"""
        try:
            import ctypes

            u = ctypes.windll.user32  # type: ignore[attr-defined]
            vx = int(u.GetSystemMetrics(76))  # SM_XVIRTUALSCREEN
            vy = int(u.GetSystemMetrics(77))  # SM_YVIRTUALSCREEN
            vw = int(u.GetSystemMetrics(78))  # SM_CXVIRTUALSCREEN
            vh = int(u.GetSystemMetrics(79))  # SM_CYVIRTUALSCREEN
            if vw > 0 and vh > 0:
                return vx, vy, vw, vh
        except Exception:
            pass
        return 0, 0, int(self.root.winfo_screenwidth()), int(self.root.winfo_screenheight())

    def _clamp_xy(self, x: int, y: int, w: Optional[int] = None, h: Optional[int] = None) -> Tuple[int, int]:
        """保证窗口完全落在虚拟桌面内（多屏并集；否则主屏）。"""
        if w is None:
            w = max(int(self.root.winfo_width()), 1)
        if h is None:
            h = max(int(self.root.winfo_height()), 1)
        w = max(int(w), 1)
        h = max(int(h), 1)
        vx, vy, vw, vh = self._virtual_screen()
        max_x = vx + vw - w
        max_y = vy + vh - h
        if max_x < vx:
            x = vx
        else:
            x = max(vx, min(int(x), max_x))
        if max_y < vy:
            y = vy
        else:
            y = max(vy, min(int(y), max_y))
        return x, y

    def _on_press(self, e) -> None:
        self._drag_x = e.x_root - self.root.winfo_x()
        self._drag_y = e.y_root - self.root.winfo_y()

    def _on_drag(self, e) -> None:
        w = max(int(self.root.winfo_width()), 1)
        h = max(int(self.root.winfo_height()), 1)
        x = e.x_root - self._drag_x
        y = e.y_root - self._drag_y
        x, y = self._clamp_xy(x, y, w, h)
        self.root.geometry(f"+{x}+{y}")

    def _sync_mini_from_total(self) -> None:
        try:
            tr = self._row_by_key("total")
            txt = str(tr["pnl"].cget("text") or "—")
            fg = str(tr["pnl"].cget("fg") or self.fg)
        except Exception:
            txt, fg = self._mini_pnl_text, self._mini_pnl_fg
        self._mini_pnl_text = txt
        self._mini_pnl_fg = fg
        self._mini.config(text=txt, fg=fg)

    def _fit_mini(self) -> None:
        if not self._hidden:
            return
        self.root.update_idletasks()
        need_w = max(int(self._mini.winfo_reqwidth()) + 8, 40)
        need_h = max(int(self._mini.winfo_reqheight()) + 4, 18)
        x, y = self._clamp_xy(self.root.winfo_x(), self.root.winfo_y(), need_w, need_h)
        self.root.geometry(f"{need_w}x{need_h}+{x}+{y}")

    def _show_mini_only(self) -> None:
        """折叠：只留合计当日盈亏小条。"""
        self._hidden = True
        self._sync_mini_from_total()
        for w in list(self.root.pack_slaves()):
            w.pack_forget()
        self._mini.pack(padx=4, pady=1)
        self._fit_mini()

    def _show_full(self) -> None:
        """展开完整列表。"""
        self._hidden = False
        self._mini.pack_forget()
        for i, r in enumerate(self.rows):
            r["frame"].pack(fill="x", padx=4, pady=(3 if i == 0 else 0, 0))
        if self._pad is None:
            self._pad = tk.Frame(self.root, height=5, bg=self.bg)
        self._pad.pack(fill="x")
        self.root.update_idletasks()
        self._fit_width()

    def _toggle_thin(self, _e=None) -> None:
        # 防重入 / 防 bindtags 双触发
        now = time.monotonic()
        last = float(getattr(self, "_last_toggle_ts", 0.0) or 0.0)
        if now - last < 0.35:
            return
        if getattr(self, "_toggling", False):
            return
        self._toggling = True
        self._last_toggle_ts = now
        x0, y0 = int(self.root.winfo_x()), int(self.root.winfo_y())
        collapsing = not self._hidden
        # 先改标志，避免并发 _paint/_fit_width 按展开态处理
        self._hidden = collapsing
        # 不用 withdraw：Windows 在 deiconify 时会恢复旧尺寸，导致折叠“闪一下又回去”
        try:
            try:
                prev_alpha = float(self.root.attributes("-alpha"))
            except Exception:
                prev_alpha = ALPHA
            try:
                self.root.attributes("-alpha", 0.01)
            except Exception:
                prev_alpha = None
            if collapsing:
                self._show_mini_only()
            else:
                self._show_full()
            self.root.update_idletasks()
            w = max(int(self.root.winfo_width()), 1)
            h = max(int(self.root.winfo_height()), 1)
            x, y = self._clamp_xy(x0, y0, w, h)
            geo = self.root.geometry()
            size = geo.split("+", 1)[0] if "x" in geo else f"{w}x{h}"
            self.root.geometry(f"{size}+{x}+{y}")
            self.root.update_idletasks()
            # 再写一次，防止布局后尺寸被冲掉
            w = max(int(self.root.winfo_width()), 1)
            h = max(int(self.root.winfo_height()), 1)
            x, y = self._clamp_xy(x0, y0, w, h)
            self.root.geometry(f"{w}x{h}+{x}+{y}")
            if prev_alpha is not None:
                try:
                    self.root.attributes("-alpha", prev_alpha)
                except Exception:
                    pass
            self.root.lift()
        finally:
            self._toggling = False

    def _popup(self, e) -> None:
        try:
            self.menu.tk_popup(e.x_root, e.y_root)
        finally:
            self.menu.grab_release()

    def _toggle_topmost(self) -> None:
        cur = bool(self.root.attributes("-topmost"))
        self.root.attributes("-topmost", not cur)

    def _force_refresh(self) -> None:
        threading.Thread(target=self._one_fetch, daemon=True).start()

    def _apply_items(self, items: List[dict]) -> None:
        """保存并热更新自选行。"""
        self._items = [_normalize_item(x) for x in items if _normalize_item(x)]
        save_items(self._items)
        self._init_states_from_items()
        self._rebuild_watch_rows()
        self._paint()
        self.root.after_idle(self._fit_width)
        threading.Thread(target=self._bootstrap, daemon=True).start()

    def _edit_amounts(self) -> None:
        """对话框：增删自选。中间列表滚动，底部「添加/保存」始终可见。"""
        win = tk.Toplevel(self.root)
        win.withdraw()
        win.title("设置持仓")
        win.attributes("-topmost", True)
        win.resizable(True, True)
        win.configure(bg="#222222")
        win.transient(self.root)

        # 先 pack 底部固定区（side=bottom），再顶部 tip + 中间可扩展列表
        btn_fr = tk.Frame(win, bg="#222222")
        btn_fr.pack(side="bottom", fill="x", pady=(8, 12))

        status = tk.Label(
            win, text="", fg="#888888", bg="#222222", font=self.font, anchor="w"
        )
        status.pack(side="bottom", fill="x", padx=12, pady=(0, 2))

        add_fr = tk.Frame(win, bg="#222222")
        add_fr.pack(side="bottom", fill="x", padx=12, pady=(6, 4))

        tip = tk.Label(
            win,
            text="标签 / 代码 / 本金(元) — 本金可留空或 0（不计盈亏）",
            fg="#bbbbbb",
            bg="#222222",
            font=self.font,
            anchor="w",
            justify="left",
        )
        tip.pack(side="top", anchor="w", padx=12, pady=(12, 6))

        wrap = tk.Frame(win, bg="#222222")
        wrap.pack(side="top", fill="both", expand=True, padx=10, pady=4)
        canvas = tk.Canvas(wrap, bg="#222222", highlightthickness=0, height=160, width=420)
        sb = tk.Scrollbar(wrap, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        body = tk.Frame(canvas, bg="#222222")
        body_id = canvas.create_window((0, 0), window=body, anchor="nw")

        def _on_body_cfg(_e=None) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas_cfg(e) -> None:
            canvas.itemconfig(body_id, width=max(int(e.width), 1))

        body.bind("<Configure>", _on_body_cfg)
        canvas.bind("<Configure>", _on_canvas_cfg)

        def _on_mousewheel(e) -> None:
            # Windows / mac / X11
            if getattr(e, "delta", 0):
                canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
            elif getattr(e, "num", None) == 4:
                canvas.yview_scroll(-1, "units")
            elif getattr(e, "num", None) == 5:
                canvas.yview_scroll(1, "units")

        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        canvas.bind_all("<Button-4>", _on_mousewheel)
        canvas.bind_all("<Button-5>", _on_mousewheel)

        def _unbind_wheel() -> None:
            try:
                canvas.unbind_all("<MouseWheel>")
                canvas.unbind_all("<Button-4>")
                canvas.unbind_all("<Button-5>")
            except Exception:
                pass

        win.protocol("WM_DELETE_WINDOW", lambda: (_unbind_wheel(), win.destroy()))

        hdr = tk.Frame(body, bg="#222222")
        hdr.pack(fill="x", pady=(0, 4))
        for txt, w in (("标签", 10), ("代码", 10), ("本金", 12), ("", 4)):
            tk.Label(
                hdr, text=txt, fg="#888888", bg="#222222", font=self.font, width=w, anchor="w"
            ).pack(side="left", padx=3)

        row_vars: List[dict] = []

        def remove_row(rv: dict) -> None:
            rv["frame"].destroy()
            if rv in row_vars:
                row_vars.remove(rv)
            win.after_idle(_relayout_list)

        def add_row(item: Optional[dict] = None) -> None:
            it = item or {"code": "", "kind": "fund", "label": "", "amount": 0.0}
            fr = tk.Frame(body, bg="#222222")
            fr.pack(fill="x", pady=3)
            e_label = tk.Entry(
                fr, width=10, font=self.font, bg="#333333", fg="#dddddd", insertbackground="#dddddd"
            )
            e_label.insert(0, str(it.get("label") or ""))
            e_label.pack(side="left", padx=3)
            e_code = tk.Entry(
                fr, width=10, font=self.font, bg="#333333", fg="#dddddd", insertbackground="#dddddd"
            )
            e_code.insert(0, str(it.get("code") or ""))
            e_code.pack(side="left", padx=3)
            e_amt = tk.Entry(
                fr, width=12, font=self.font, bg="#333333", fg="#dddddd", insertbackground="#dddddd"
            )
            amt = it.get("amount") or 0
            e_amt.insert(
                0,
                ""
                if float(amt) == 0
                else str(int(amt) if float(amt) == int(float(amt)) else amt),
            )
            e_amt.pack(side="left", padx=3)
            rv = {
                "frame": fr,
                "label": e_label,
                "code": e_code,
                "amount": e_amt,
                "kind": it.get("kind") or "fund",
                "meta": dict(it),
            }
            tk.Button(fr, text="删", width=4, command=lambda r=rv: remove_row(r)).pack(
                side="left", padx=3
            )
            row_vars.append(rv)

        for it in self._items:
            add_row(it)

        tk.Label(add_fr, text="添加代码", fg="#aaaaaa", bg="#222222", font=self.font).pack(
            side="left"
        )
        e_new = tk.Entry(
            add_fr, width=12, font=self.font, bg="#333333", fg="#dddddd", insertbackground="#dddddd"
        )
        e_new.pack(side="left", padx=8)

        def on_add() -> None:
            code = e_new.get().strip()
            if not code:
                return
            dig = re.sub(r"\D", "", code).zfill(6)[-6:] if re.sub(r"\D", "", code) else ""
            for rv in row_vars:
                c0 = rv["code"].get().strip()
                if c0 == code or (dig and c0.zfill(6) == dig):
                    status.config(text="已存在该代码", fg="#8f5a5a")
                    return
            status.config(text="识别中…", fg="#888888")
            win.update_idletasks()

            def work() -> None:
                try:
                    info = resolve_instrument(code)
                    err = None
                except Exception as ex:
                    info, err = None, str(ex)

                def done() -> None:
                    if err or not info:
                        status.config(text=err or "识别失败", fg="#8f5a5a")
                        return
                    add_row(
                        {
                            "code": info["code"],
                            "kind": info["kind"],
                            "label": info["label"],
                            "amount": 0.0,
                            "sina_key": info.get("sina_key"),
                            "name": info.get("name"),
                        }
                    )
                    e_new.delete(0, "end")
                    kind_cn = "基金" if info["kind"] == "fund" else "股票"
                    status.config(
                        text=f"已添加 {kind_cn} {info['code']} {info['label']}", fg="#5a8f6a"
                    )
                    win.after_idle(lambda: _relayout_list(scroll_bottom=True))

                win.after(0, done)

            threading.Thread(target=work, daemon=True).start()

        tk.Button(add_fr, text="添加", width=8, command=on_add).pack(side="left")
        e_new.bind("<Return>", lambda _e: on_add())

        def on_save() -> None:
            new_items: List[dict] = []
            try:
                for rv in row_vars:
                    code = rv["code"].get().strip()
                    if not code:
                        continue
                    label = rv["label"].get().strip() or code
                    raw_amt = rv["amount"].get().strip().replace(",", "")
                    amount = float(raw_amt) if raw_amt else 0.0
                    if amount < 0:
                        raise ValueError("本金不能为负")
                    meta = rv.get("meta") or {}
                    kind = rv.get("kind") or meta.get("kind") or "fund"
                    old_code = str(meta.get("code") or "")
                    item = {
                        "code": code,
                        "kind": kind,
                        "label": label,
                        "amount": amount,
                    }
                    if meta.get("sina_key") and code == old_code:
                        item["sina_key"] = meta["sina_key"]
                    if meta.get("name") and code == old_code:
                        item["name"] = meta["name"]
                    if code != old_code:
                        info = resolve_instrument(code)
                        item["code"] = info["code"]
                        item["kind"] = info["kind"]
                        if not rv["label"].get().strip():
                            item["label"] = info["label"]
                        if info.get("sina_key"):
                            item["sina_key"] = info["sina_key"]
                        if info.get("name"):
                            item["name"] = info["name"]
                    new_items.append(item)
            except Exception as ex:
                messagebox.showerror("格式错误", f"请检查代码与本金\n{ex}", parent=win)
                return
            _unbind_wheel()
            win.destroy()
            self._apply_items(new_items)

        def on_cancel() -> None:
            _unbind_wheel()
            win.destroy()

        pad_l = tk.Frame(btn_fr, bg="#222222")
        pad_r = tk.Frame(btn_fr, bg="#222222")
        pad_l.pack(side="left", expand=True, fill="x")
        tk.Button(btn_fr, text="保存", command=on_save, width=10).pack(side="left", padx=8)
        tk.Button(btn_fr, text="取消", command=on_cancel, width=10).pack(side="left", padx=8)
        pad_r.pack(side="left", expand=True, fill="x")

        LIST_MAX_H = 360
        LIST_MIN_H = 120

        def _relayout_list(scroll_bottom: bool = False) -> None:
            """仅调整列表区高度；窗口总高有上限，超出则列表内滚动，页脚不动。"""
            win.update_idletasks()
            body.update_idletasks()
            list_h = max(int(body.winfo_reqheight()), 36)
            canvas_h = min(max(list_h, LIST_MIN_H), LIST_MAX_H)
            tip_w = int(tip.winfo_reqwidth())
            row_w = max(int(body.winfo_reqwidth()), 400)
            canvas_w = max(tip_w, row_w, 420)
            canvas.configure(height=canvas_h, width=canvas_w)
            canvas.itemconfig(body_id, width=canvas_w)
            canvas.configure(scrollregion=canvas.bbox("all") or (0, 0, canvas_w, list_h))
            win.update_idletasks()
            footer_h = (
                max(add_fr.winfo_reqheight(), 1)
                + max(status.winfo_reqheight(), 1)
                + max(btn_fr.winfo_reqheight(), 1)
                + 28
            )
            tip_h = max(tip.winfo_reqheight(), 1) + 18
            need_h = tip_h + canvas_h + footer_h + 24
            need_w = max(tip_w + 40, canvas_w + 48, 480)
            sw = win.winfo_screenwidth()
            sh = win.winfo_screenheight()
            max_h = max(320, sh - 80)
            need_h = min(max(need_h, 320), max_h)
            # 若窗口已被压到上限，列表用剩余高度滚动
            avail_list = need_h - tip_h - footer_h - 24
            if avail_list < canvas_h:
                canvas_h = max(LIST_MIN_H, avail_list)
                canvas.configure(height=canvas_h)
            win.minsize(480, 320)
            try:
                fx = int(self.root.winfo_rootx())
                fy = int(self.root.winfo_rooty())
                fw = max(int(self.root.winfo_width()), 1)
                fh = max(int(self.root.winfo_height()), 1)
                x = fx + (fw - need_w) // 2
                y = fy + (fh - need_h) // 2
            except Exception:
                x = (sw - need_w) // 2
                y = (sh - need_h) // 2
            if x < 8 or y < 8 or x + need_w > sw - 8 or y + need_h > sh - 8:
                x = (sw - need_w) // 2
                y = (sh - need_h) // 2
            x = max(8, min(x, sw - need_w - 8))
            y = max(8, min(y, sh - need_h - 8))
            win.geometry(f"{need_w}x{need_h}+{x}+{y}")
            canvas.configure(scrollregion=canvas.bbox("all") or (0, 0, canvas_w, list_h))
            if scroll_bottom:
                canvas.yview_moveto(1.0)

        _relayout_list()
        win.update_idletasks()
        _relayout_list()
        win.deiconify()
        win.lift()
        win.grab_set()
        e_new.focus_set()

    def _one_fetch(self) -> None:
        try:
            with self._lock:
                items = [dict(x) for x in self._items]
                states = {c: dict(s) for c, s in self._fund_state.items()}
                stock_keys = dict(self._stock_keys)

            codes = ["rt_hkHSTECH", "s_sh000001"]
            for st in states.values():
                codes.extend(holdings_to_sina_codes(st.get("holdings") or []))
            for code, sk in stock_keys.items():
                if sk:
                    codes.append(sk)
                else:
                    codes.extend(sina_keys_for_stock(code))

            seen = set()
            uniq = []
            for c in codes:
                if c not in seen:
                    seen.add(c)
                    uniq.append(c)
            batch = _sina_batch(uniq)
            hstech = fetch_hstech(batch)
            sh = fetch_shanghai(batch)

            fund_snaps: Dict[str, dict] = {}
            stock_snaps: Dict[str, dict] = {}

            for it in items:
                code = it["code"]
                if it.get("kind") == "stock":
                    sk = stock_keys.get(code) or ""
                    fields = batch.get(sk) if sk else None
                    if not fields:
                        # 再试备选 key
                        for k in sina_keys_for_stock(code):
                            if k in batch:
                                fields = batch[k]
                                sk = k
                                break
                    if not fields:
                        stock_snaps[code] = {"label": it.get("label") or code, "pct": 0.0, "price": None}
                        continue
                    try:
                        if sk.startswith("rt_hk"):
                            price, _ch, pct = _pct_from_hk(fields)
                        else:
                            price, _ch, pct = _pct_from_a(fields)
                    except Exception:
                        stock_snaps[code] = {"label": it.get("label") or code, "pct": 0.0, "price": None}
                        continue
                    stock_snaps[code] = {
                        "label": it.get("label") or code,
                        "pct": pct,
                        "price": price,
                    }
                    with self._lock:
                        self._stock_keys[code] = sk
                else:
                    st = states.get(code) or {"holdings": [], "prev_nav": None}
                    prev_nav = st.get("prev_nav")
                    if prev_nav is None:
                        try:
                            nav, day = fetch_prev_nav_for_estimate(code)
                            prev_nav = nav
                            with self._lock:
                                if code in self._fund_state:
                                    self._fund_state[code]["prev_nav"] = nav
                                    self._fund_state[code]["nav_date"] = day
                        except Exception:
                            pass
                    holdings = st.get("holdings") or []
                    est_pct, est_nav, used, covered, drag, boost = estimate_fund(
                        holdings, batch, prev_nav
                    )
                    fund_snaps[code] = {
                        "label": it.get("label") or code,
                        "est_pct": est_pct,
                        "est_nav": est_nav,
                        "used": used,
                        "covered": covered,
                        "drag": drag,
                        "boost": boost,
                    }

            with self._lock:
                self._snap = {
                    "hstech": hstech,
                    "sh": sh,
                    "funds": fund_snaps,
                    "stocks": stock_snaps,
                }
                self._err_streak = 0
                states_now = {c: dict(s) for c, s in self._fund_state.items()}
            try:
                self._maybe_log_close_estimates(items, fund_snaps, states_now)
            except Exception:
                pass
            try:
                # 收盘后顺带回填近期官方净值
                if not is_market_open():
                    fill_official_for_log()
            except Exception:
                pass
            self.root.after(0, self._paint)
        except Exception:
            with self._lock:
                self._err_streak += 1
            self.root.after(0, self._paint)

    def _poll_loop(self) -> None:
        """开盘 4s 刷新；收盘降频。长 sleep 分段，开盘后立刻醒来，避免早盘/午休卡住。"""
        time.sleep(1.0)
        while not self._stop:
            open_now = is_market_open()
            delay = POLL_OPEN_SEC if open_now else POLL_CLOSED_SEC
            with self._lock:
                streak = self._err_streak
            if streak >= 3:
                delay = max(delay, 30.0)
            # 分段睡：收盘最长 900s，但每 5s 检查是否已开盘
            chunk = 5.0 if not open_now else delay
            slept = 0.0
            while slept < delay and not self._stop:
                step = min(chunk, delay - slept)
                time.sleep(step)
                slept += step
                if not open_now and is_market_open():
                    break
            if self._stop:
                break
            self._one_fetch()

    def _color(self, pct: float, closed: bool = False) -> str:
        # 收盘仍保留红绿，便于扫一眼；「收」另列提示
        if pct > 0.0005:
            return self.fg_up
        if pct < -0.0005:
            return self.fg_dn
        return self.fg_flat

    def _fmt_price(self, price: Optional[float]) -> str:
        if price is None:
            return ""
        if price >= 1000:
            return f"{price:,.2f}"
        if price >= 100:
            return f"{price:.2f}"
        if price >= 10:
            return f"{price:.2f}"
        return f"{price:.4f}"

    def _fmt_pct(self, pct: float) -> str:
        sign = "+" if pct > 0 else ""
        return f"{sign}{pct:.2f}%"

    def _fmt_pnl(self, amount: float, est_pct: float, *, closed: bool = False) -> Tuple[str, str]:
        pnl = amount * est_pct / 100.0
        n = int(round(pnl))
        if n > 0:
            text = f"+{n}"
        elif n < 0:
            text = f"{n}"
        else:
            text = "0"
        return text, self._color(est_pct)

    def _set_row(
        self,
        r: dict,
        *,
        label: Optional[str] = None,
        price: Optional[float] = None,
        pct: Optional[float] = None,
        closed: bool = False,
        pnl_text: str = "—",
        pnl_fg: Optional[str] = None,
        price_text: Optional[str] = None,
        price_fg: Optional[str] = None,
        drag_text: Optional[str] = None,
        drag_fg: Optional[str] = None,
        boost_text: Optional[str] = None,
        boost_fg: Optional[str] = None,
    ) -> None:
        if label is not None:
            r["lab"].config(text=label[: self.LABEL_MAX], fg=self.fg)
        # drag 列：基金贡献 / 指数价格
        if drag_text is not None:
            r["drag"].config(text=drag_text, fg=drag_fg or self.fg)
        elif price_text is not None:
            r["drag"].config(text=price_text, fg=price_fg or self.fg)
        elif price is not None:
            r["drag"].config(text=self._fmt_price(price), fg=price_fg or self.fg)
        else:
            r["drag"].config(text="", fg=self.fg)
        if boost_text is not None:
            r["boost"].config(text=boost_text, fg=boost_fg or self.fg)
        else:
            r["boost"].config(text="", fg=self.fg)
        if pct is None:
            r["pct"].config(text="", fg=self.fg)
        else:
            r["pct"].config(text=self._fmt_pct(pct), fg=self._color(pct))
        r["mark"].config(text="收" if closed else "", fg=self.fg)
        r["pnl"].config(text=pnl_text, fg=pnl_fg or self.fg)

    def _row_by_key(self, key: str) -> dict:
        for r in self.rows:
            if r["key"] == key:
                return r
        raise KeyError(key)

    def _paint(self) -> None:
        with self._lock:
            snap = dict(self._snap)
            err = self._err_streak
            items = [dict(x) for x in self._items]

        if not snap:
            msg = "加载中" if err == 0 else "暂无数据"
            for r in self.rows:
                self._set_row(
                    r,
                    label=r["title"],
                    price_text="",
                    pct=None,
                    closed=False,
                    pnl_text="—",
                )
                r["pct"].config(text=msg[: self.COL_PCT], fg=self.fg)
            if self._hidden:
                self.root.after_idle(self._fit_mini)
            else:
                self.root.after_idle(self._fit_width)
            return

        hk_closed = not is_hk_session()
        cn_closed = not is_cn_session()
        both_closed = not is_market_open()

        hp, _hc, hpct = snap["hstech"]  # type: ignore
        sp, _sc, spct = snap["sh"]  # type: ignore

        try:
            self._set_row(
                self._row_by_key("sh"),
                label="上证",
                price=float(sp),
                pct=float(spct),
                closed=cn_closed,
            )
            self._set_row(
                self._row_by_key("hstech"),
                label="恒科",
                price=float(hp),
                pct=float(hpct),
                closed=hk_closed,
            )
        except KeyError:
            pass

        funds = snap.get("funds") or {}
        stocks = snap.get("stocks") or {}
        total_pnl = 0.0

        for it in items:
            code = it["code"]
            label = it.get("label") or code
            amount = float(it.get("amount") or 0.0)
            try:
                r = self._row_by_key(code)
            except KeyError:
                continue

            if it.get("kind") == "stock":
                ss = stocks.get(code) or {}
                pct = float(ss.get("pct") or 0.0)
                price = ss.get("price")
                closed = (
                    hk_closed
                    if str(self._stock_keys.get(code, "")).startswith("rt_hk")
                    else cn_closed
                )
                if amount > 0:
                    total_pnl += amount * pct / 100.0
                    pt, pc = self._fmt_pnl(amount, pct)
                else:
                    pt, pc = "—", self.fg
                self._set_row(
                    r,
                    label=label,
                    price=float(price) if price is not None else None,
                    pct=pct,
                    closed=closed,
                    pnl_text=pt,
                    pnl_fg=pc,
                )
            else:
                fs = funds.get(code) or {}
                est_pct = float(fs.get("est_pct") or 0.0)
                drag_txt, drag_c = fmt_contrib_cell(fs.get("drag"))
                boost_txt, boost_c = fmt_contrib_cell(fs.get("boost"))
                if amount > 0:
                    total_pnl += amount * est_pct / 100.0
                    pt, pc = self._fmt_pnl(amount, est_pct)
                else:
                    pt, pc = "—", self.fg
                self._set_row(
                    r,
                    label=label,
                    drag_text=drag_txt or "—",
                    drag_fg=self._color(drag_c) if drag_txt else self.fg,
                    boost_text=boost_txt or "—",
                    boost_fg=self._color(boost_c) if boost_txt else self.fg,
                    pct=est_pct,
                    closed=both_closed,
                    pnl_text=pt,
                    pnl_fg=pc,
                )

        try:
            tr = self._row_by_key("total")
            n = int(round(total_pnl))
            if n > 0:
                tt, tc = f"+{n}", self.fg_up
            elif n < 0:
                tt, tc = f"{n}", self.fg_dn
            else:
                tt, tc = "0", self.fg_flat
            self._set_row(
                tr,
                label="合计",
                price_text="",
                pct=None,
                closed=False,
                pnl_text=tt,
                pnl_fg=tc,
            )
            self._mini_pnl_text = tt
            self._mini_pnl_fg = tc
            if self._hidden:
                self._mini.config(text=tt, fg=tc)
        except KeyError:
            pass

        try:
            self._curve_sync_live()
        except Exception:
            pass

        if self._hidden:
            self.root.after_idle(self._fit_mini)
        else:
            self.root.after_idle(self._fit_width)

    def _fit_width(self) -> None:
        if self._hidden:
            return
        self.root.update_idletasks()
        widths = []
        for r in self.rows:
            widths.append(r["frame"].winfo_reqwidth())
        need_w = max(widths) + 6 if widths else WIN_W
        need_w = max(need_w, 130)
        need_h = sum(w.winfo_reqheight() for w in self.root.pack_slaves())
        need_h = max(need_h, 90)
        x = self.root.winfo_x()
        y = self.root.winfo_y()
        sw = self.root.winfo_screenwidth()
        if abs((x + self.root.winfo_width() + MARGIN) - sw) < 40:
            x = sw - need_w - MARGIN
        x, y = self._clamp_xy(x, y, need_w, need_h)
        self.root.geometry(f"{need_w}x{need_h}+{x}+{y}")

    def _maybe_log_close_estimates(
        self,
        items: List[dict],
        fund_snaps: Dict[str, dict],
        states: Dict[str, dict],
        *,
        force: bool = False,
        ignore_window: bool = False,
    ) -> int:
        """按基金收盘窗口落盘估值：A 股向 15:05，港股向 16:10；同日同代码不覆盖。"""
        date_s = _trade_date_str()
        n = 0
        for it in items:
            if it.get("kind") == "stock":
                continue
            code = it["code"]
            fs = fund_snaps.get(code) or {}
            if not fs:
                continue
            st = states.get(code) or {}
            fd = st.get("fund") or {}
            label = str(it.get("label") or fs.get("label") or code)
            name = str(fd.get("name") or "")
            holdings = st.get("holdings") or fd.get("holdings") or []
            if not force and not ignore_window:
                if not should_snapshot_close_for_fund(
                    holdings, fund=fd, label=label, name=name
                ):
                    continue
            est_pct = float(fs.get("est_pct") or 0.0)
            ok = append_close_estimate(
                date_s=date_s,
                code=code,
                label=label,
                est_pct=est_pct,
                est_nav=fs.get("est_nav"),
                prev_nav=st.get("prev_nav"),
                nav_date=str(st.get("nav_date") or ""),
                covered=float(fs.get("covered") or 0.0),
                used=int(fs.get("used") or 0),
                force=force,
            )
            if ok:
                n += 1
        return n

    def _open_log_dir(self) -> None:
        try:
            _ensure_est_log()
            import os
            os.startfile(str(EST_LOG_PATH.parent))  # type: ignore[attr-defined]
        except Exception as e:
            messagebox.showerror("打开失败", str(e), parent=self.root)

    def _show_today_curve(self) -> None:
        """右键：当日分时曲线。已打开则提到前台并刷新。"""
        win = getattr(self, "_curve_win", None)
        if win is not None:
            try:
                if win.winfo_exists():
                    win.lift()
                    self._curve_reload(force=True)
                    return
            except Exception:
                self._curve_win = None
        self._curve_dialog()

    def _curve_dialog(self) -> None:
        win = tk.Toplevel(self.root)
        self._curve_win = win
        win.withdraw()
        win.title("今日曲线")
        win.configure(bg=self.bg)
        win.attributes("-topmost", True)
        win.transient(self.root)
        win.resizable(True, True)

        tab_fr = tk.Frame(win, bg=self.bg)
        tab_fr.pack(fill="x", padx=10, pady=(10, 2))
        head = tk.Label(
            win,
            text="加载中…",
            font=self.font,
            fg="#cccccc",
            bg=self.bg,
            anchor="w",
            justify="left",
        )
        head.pack(fill="x", padx=10, pady=(4, 2))
        canvas = tk.Canvas(win, bg=self.bg, highlightthickness=0, height=260)
        canvas.pack(fill="both", expand=True, padx=10, pady=4)
        tip = tk.Label(
            win,
            text="指数/股票为官方分时；基金由持仓分时加权估值，仅供盯盘。左键悬停看数值。",
            font=self.font,
            fg=self.fg,
            bg=self.bg,
            anchor="w",
        )
        tip.pack(fill="x", padx=10)
        btn_fr = tk.Frame(win, bg=self.bg)
        btn_fr.pack(fill="x", padx=10, pady=(4, 10))
        tk.Button(btn_fr, text="刷新", command=lambda: self._curve_reload(force=True)).pack(side="right", padx=(6, 0))
        tk.Button(btn_fr, text="关闭", command=lambda: _on_close()).pack(side="right")

        state = {
            "tabs": [],  # list of dicts
            "current": "",
            "hover": None,
            "drawn": [],  # (x, y, hm, val)
            "job": None,
            "loading": False,
            "axis_kind": "mix",
        }
        self._curve_state = state
        tab_btns: Dict[str, tk.Label] = {}

        def _on_close() -> None:
            job = state.get("job")
            if job is not None:
                try:
                    win.after_cancel(job)
                except Exception:
                    pass
            try:
                if getattr(self, "_curve_win", None) is win:
                    self._curve_win = None
            except Exception:
                pass
            win.destroy()

        win.protocol("WM_DELETE_WINDOW", _on_close)

        def _paint_tabs() -> None:
            for child in tab_fr.winfo_children():
                child.destroy()
            tab_btns.clear()
            for tab in state["tabs"]:
                key = tab["key"]
                sel = key == state["current"]
                lb = tk.Label(
                    tab_fr,
                    text=tab["title"],
                    font=("Segoe UI", 9, "bold" if sel else "normal"),
                    fg="#cccccc" if sel else self.fg,
                    bg="#2a2a2a" if sel else self.bg,
                    padx=8,
                    pady=3,
                    cursor="hand2",
                )
                lb.pack(side="left", padx=(0, 4))
                lb.bind("<Button-1>", lambda e, k=key: _select(k))
                tab_btns[key] = lb

        def _select(key: str) -> None:
            if key == state["current"]:
                return
            state["current"] = key
            state["hover"] = None
            _paint_tabs()
            _draw()

        def _cur_tab() -> Optional[dict]:
            for tab in state["tabs"]:
                if tab["key"] == state["current"]:
                    return tab
            return state["tabs"][0] if state["tabs"] else None

        def _fmt_val(val: Optional[float], unit: str) -> str:
            if val is None:
                return "—"
            if unit == "pnl":
                return f"{val:+,.0f}"
            return f"{val:+.2f}%"

        def _stats(points: List[Tuple[str, Optional[float]]]):
            vals = [v for _, v in points if v is not None]
            if not vals:
                return None, None, None
            return vals[-1], max(vals), min(vals)

        def _header_text(tab: Optional[dict], hover=None) -> str:
            if not tab:
                return "暂无数据"
            last, hi, lo = _stats(tab.get("points") or [])
            unit = tab.get("unit") or "pct"
            if hover and hover[0] and hover[1] is not None:
                return (
                    f"{tab['title']}  {hover[0]}  {_fmt_val(hover[1], unit)}"
                    f"    现 {_fmt_val(last, unit)}   高 {_fmt_val(hi, unit)}   低 {_fmt_val(lo, unit)}"
                )
            return (
                f"{tab['title']}  现 {_fmt_val(last, unit)}"
                f"   高 {_fmt_val(hi, unit)}   低 {_fmt_val(lo, unit)}"
            )

        def _y_range(vals: List[float], unit: str) -> Tuple[float, float]:
            if not vals:
                pad = 1.0 if unit == "pct" else 10.0
                return -pad, pad
            lo, hi = min(vals), max(vals)
            # 始终包含 0 轴
            lo = min(lo, 0.0)
            hi = max(hi, 0.0)
            if lo == hi == 0.0:
                pad = 0.5 if unit == "pct" else 10.0
                return -pad, pad
            span = hi - lo
            pad = span * 0.12 if span > 0 else (0.5 if unit == "pct" else 10.0)
            return lo - pad, hi + pad

        def _x_layout(axis: List[str], kind: str, x0: float, x1: float):
            """把交易时段映射到 x；午休不占宽度，上下午直接相邻。"""
            if kind == "cn":
                times = [t for t in axis if t <= "11:30" or t >= "13:00"]
            else:
                times = [t for t in axis if t <= "12:00" or t >= "13:00"]
            n = max(len(times), 1)
            usable = max(x1 - x0, 1.0)
            w = usable / n
            pos: Dict[str, float] = {}
            x = x0
            for t in times:
                pos[t] = x
                x += w
            return pos

        def _draw() -> None:
            canvas.delete("all")
            state["drawn"] = []
            tab = _cur_tab()
            head.config(text=_header_text(tab, state.get("hover")))
            w = max(int(canvas.winfo_width()), 1)
            h = max(int(canvas.winfo_height()), 1)
            if w < 40 or h < 40:
                return
            if not tab:
                canvas.create_text(w / 2, h / 2, text="暂无数据", fill=self.fg, font=self.font)
                return
            points = list(tab.get("points") or [])
            vals = [v for _, v in points if v is not None]
            if not vals:
                canvas.create_text(
                    w / 2, h / 2, text="今日暂无分时（未开盘或暂不可用）", fill=self.fg, font=self.font
                )
                return
            unit = tab.get("unit") or "pct"
            axis = [t for t, _ in points]
            kind = tab.get("axis") or "cn"
            pad_l, pad_r, pad_t, pad_b = 50, 12, 10, 26
            x0, x1 = pad_l, w - pad_r
            y0, y1 = pad_t, h - pad_b
            ymin, ymax = _y_range(vals, unit)
            ypos = _x_layout(axis, kind, x0, x1)

            def Y(v: float) -> float:
                if ymax == ymin:
                    return (y0 + y1) / 2
                return y1 - (v - ymin) / (ymax - ymin) * (y1 - y0)

            # 网格与 0 轴
            grid_fg = "#2e2e2e"
            zero_y = Y(0.0)
            canvas.create_line(x0, zero_y, x1, zero_y, fill="#555555")
            ticks = 4
            for i in range(ticks + 1):
                v = ymin + (ymax - ymin) * i / ticks
                y = Y(v)
                if abs(v) < 1e-9:
                    continue
                canvas.create_line(x0, y, x1, y, fill=grid_fg)
                label = f"{v:+,.0f}" if unit == "pnl" else f"{v:+.2f}"
                canvas.create_text(x0 - 6, y, text=label, fill=self.fg, font=("Consolas", 8), anchor="e")
            canvas.create_text(
                x0 - 6, zero_y, text="0", fill=self.fg_flat, font=("Consolas", 8), anchor="e"
            )

            # 时间刻度（午休已去掉，11:30/12:00 与 13:00 相邻，不再标 13:00）
            labels = ["09:30"]
            if kind == "cn":
                labels += ["11:30", "15:00"]
            else:
                labels += ["12:00", "16:00"]
            for lb in labels:
                if lb in ypos:
                    canvas.create_text(ypos[lb], y1 + 10, text=lb, fill=self.fg, font=("Consolas", 8))

            # 上下午连成一段，午休不留空
            segs = [[(t, v) for t, v in points if v is not None and t in ypos]]

            def _split_zero(seg):
                """在 0 轴交叉处切开，返回 [(unit, pts)]，pts 为 (x,y,val,hm)。"""
                raw = []
                for t, v in seg:
                    x = ypos.get(t)
                    if x is None:
                        continue
                    raw.append((x, Y(v), v, t))
                if not raw:
                    return []
                chunks = []
                cur = [raw[0]]
                for i in range(1, len(raw)):
                    x0_, y0_, v0, t0 = raw[i - 1]
                    x1_, y1_, v1, t1 = raw[i]
                    if v0 == 0 or v1 == 0 or (v0 > 0) == (v1 > 0):
                        cur.append(raw[i])
                        continue
                    # 线性插值过零
                    if v1 != v0:
                        r = (0 - v0) / (v1 - v0)
                        xz = x0_ + (x1_ - x0_) * r
                        yz = Y(0.0)
                        cur.append((xz, yz, 0.0, t0))
                        chunks.append(cur)
                        cur = [(xz, yz, 0.0, t1), raw[i]]
                    else:
                        cur.append(raw[i])
                if cur:
                    chunks.append(cur)
                return chunks

            for seg in segs:
                for chunk in _split_zero(seg):
                    if len(chunk) < 2:
                        if chunk:
                            x, y, v, t = chunk[0]
                            col = self.fg_up if v >= 0 else self.fg_dn
                            canvas.create_oval(x - 1.5, y - 1.5, x + 1.5, y + 1.5, fill=col, outline="")
                            state["drawn"].append((x, y, t, v))
                        continue
                    xs_ys = []
                    for x, y, v, t in chunk:
                        xs_ys.extend([x, y])
                        state["drawn"].append((x, y, t, v))
                    col = self.fg_up if chunk[1][2] > 0 or (chunk[1][2] == 0 and chunk[0][2] >= 0 and chunk[-1][2] >= 0) else self.fg_dn
                    # 用多数符号着色
                    mid_v = chunk[len(chunk) // 2][2]
                    if mid_v == 0:
                        mid_v = chunk[-1][2]
                    col = self.fg_up if mid_v >= 0 else self.fg_dn
                    poly = [chunk[0][0], zero_y]
                    for x, y, v, t in chunk:
                        poly += [x, y]
                    poly += [chunk[-1][0], zero_y]
                    fill = "#3a2222" if col == self.fg_up else "#1e2e24"
                    canvas.create_polygon(poly, fill=fill, outline="")
                    canvas.create_line(*xs_ys, fill=col, width=1.6, smooth=False)

            # 最新点
            last_pt = None
            for t, v in reversed(points):
                if v is not None and t in ypos:
                    last_pt = (ypos[t], Y(v), t, v)
                    break
            if last_pt:
                x, y, t, v = last_pt
                col = self.fg_up if v >= 0 else self.fg_dn
                canvas.create_oval(x - 3, y - 3, x + 3, y + 3, fill=col, outline="")

            # 悬停十字
            hover = state.get("hover")
            if hover and hover[0] in ypos and hover[1] is not None:
                hx, hy = ypos[hover[0]], Y(hover[1])
                canvas.create_line(hx, y0, hx, y1, fill="#666666", dash=(2, 2))
                canvas.create_line(x0, hy, x1, hy, fill="#666666", dash=(2, 2))

        def _on_move(e) -> None:
            drawn = state.get("drawn") or []
            if not drawn:
                return
            best = None
            best_d = 14
            for x, y, t, v in drawn:
                d = abs(x - e.x)
                if d < best_d:
                    best_d = d
                    best = (t, v)
            if best != state.get("hover"):
                state["hover"] = best
                _draw()

        def _on_leave(_e) -> None:
            if state.get("hover") is not None:
                state["hover"] = None
                _draw()

        canvas.bind("<Motion>", _on_move)
        canvas.bind("<Leave>", _on_leave)
        canvas.bind("<Configure>", lambda _e: _draw())

        def _schedule() -> None:
            job = state.get("job")
            if job is not None:
                try:
                    win.after_cancel(job)
                except Exception:
                    pass
            # 开盘约 30 秒刷新一次
            delay = 30000 if is_market_open() else 180000
            state["job"] = win.after(delay, lambda: self._curve_reload(force=False))

        self._curve_paint_tabs = _paint_tabs
        self._curve_draw = _draw
        self._curve_header = head
        self._curve_schedule = _schedule
        self._curve_select = _select

        win.update_idletasks()
        need_w, need_h = 640, 380
        sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
        x, y = (sw - need_w) // 2, (sh - need_h) // 2
        x = max(8, min(x, sw - need_w - 8))
        y = max(8, min(y, sh - need_h - 8))
        win.geometry(f"{need_w}x{need_h}+{x}+{y}")
        win.deiconify()
        win.lift()
        self._curve_reload(force=False)

    def _curve_reload(self, force: bool = False) -> None:
        win = getattr(self, "_curve_win", None)
        state = getattr(self, "_curve_state", None)
        if win is None or state is None:
            return
        try:
            if not win.winfo_exists():
                return
        except Exception:
            return
        if state.get("loading"):
            return
        state["loading"] = True
        if force:
            _invalidate_trend_cache()
        head = getattr(self, "_curve_header", None)
        if head is not None:
            try:
                head.config(text="加载中…")
            except Exception:
                pass

        def work() -> None:
            try:
                tabs = self._build_today_curves()
            except Exception:
                tabs = []
            def apply() -> None:
                state["loading"] = False
                try:
                    if not win.winfo_exists():
                        return
                except Exception:
                    return
                prev = state.get("current") or ""
                state["tabs"] = tabs
                keys = [t["key"] for t in tabs]
                if prev in keys:
                    state["current"] = prev
                elif tabs:
                    state["current"] = tabs[0]["key"]
                else:
                    state["current"] = ""
                state["hover"] = None
                try:
                    self._curve_paint_tabs()
                    self._curve_draw()
                    self._curve_schedule()
                except Exception:
                    pass
            self.root.after(0, apply)

        threading.Thread(target=work, daemon=True).start()

    def _build_today_curves(self) -> List[dict]:
        with self._lock:
            items = [dict(x) for x in self._items]
            states = {c: dict(s) for c, s in self._fund_state.items()}
            stock_keys = dict(self._stock_keys)

        secids: List[str] = ["1.000001", "124.HSTECH"]
        fund_meta: List[dict] = []
        for it in items:
            code = it["code"]
            if it.get("kind") == "stock":
                sk = stock_keys.get(code) or ""
                sid = _secid_from_sina_key(sk) if sk else None
                if not sid:
                    # 兜底：按代码猜市场
                    raw = str(code)
                    if len(re.sub(r"\D", "", raw)) == 5 or raw.upper().startswith("HK"):
                        sid = _em_secid("hk", raw)
                    else:
                        sid = _secid_from_sina_key((sina_keys_for_stock(raw) or [""])[0])
                if sid:
                    secids.append(sid)
                    it["_sid"] = sid
            else:
                st = states.get(code) or {}
                holdings = list(st.get("holdings") or [])
                hk = fund_is_hk_heavy(
                    holdings,
                    fund=st.get("fund"),
                    label=str(it.get("label") or ""),
                )
                for market, c, _n, _w in holdings:
                    sid = _em_secid(market, c)
                    if sid:
                        secids.append(sid)
                fund_meta.append({"item": it, "holdings": holdings, "hk": hk})

        trends = fetch_minute_trends(secids)
        cap = _curve_cap_hm(trends)

        tabs: List[dict] = []
        mix_axis = SESSION_AXES["mix"]
        cn_axis = SESSION_AXES["cn"]
        hk_axis = SESSION_AXES["hk"]

        fund_curves_mix: Dict[str, List[Tuple[str, Optional[float]]]] = {}
        fund_curves_own: Dict[str, dict] = {}
        for meta in fund_meta:
            it = meta["item"]
            code = it["code"]
            axis_kind = "hk" if meta["hk"] else "cn"
            axis = hk_axis if meta["hk"] else cn_axis
            own = _clip_curve(_fund_curve(meta["holdings"], trends, axis), cap)
            mix = _clip_curve(_fund_curve(meta["holdings"], trends, mix_axis), cap)
            fund_curves_mix[code] = mix
            fund_curves_own[code] = {"axis": axis_kind, "points": own, "label": it.get("label") or code}

        stock_curves_mix: Dict[str, List[Tuple[str, Optional[float]]]] = {}
        stock_own: List[dict] = []
        for it in items:
            if it.get("kind") != "stock":
                continue
            sid = it.get("_sid")
            tr = trends.get(sid) if sid else None
            # 判断港股还是 A 股
            sk = stock_keys.get(it["code"]) or ""
            is_hk = "hk" in sk.lower() or (sid or "").startswith("116.")
            axis_kind = "hk" if is_hk else "cn"
            axis = hk_axis if is_hk else cn_axis
            own = _clip_curve(_align_pct(tr, axis) if tr else [(t, None) for t in axis], cap)
            mix = _clip_curve(_align_pct(tr, mix_axis) if tr else [(t, None) for t in mix_axis], cap)
            stock_curves_mix[it["code"]] = mix
            stock_own.append(
                {
                    "code": it["code"],
                    "label": it.get("label") or it["code"],
                    "axis": axis_kind,
                    "points": own,
                }
            )

        has_amount = any(float(it.get("amount") or 0) for it in items)
        if has_amount:
            tabs.append(
                {
                    "key": "total",
                    "title": "合计",
                    "unit": "pnl",
                    "axis": "mix",
                    "points": _clip_curve(
                        _total_pnl_curve(items, fund_curves_mix, stock_curves_mix, mix_axis), cap
                    ),
                }
            )

        sh_tr = trends.get("1.000001")
        tabs.append(
            {
                "key": "sh",
                "title": "上证",
                "unit": "pct",
                "axis": "cn",
                "points": _clip_curve(
                    _align_pct(sh_tr, cn_axis) if sh_tr else [(t, None) for t in cn_axis], cap
                ),
            }
        )
        hk_tr = trends.get("124.HSTECH")
        tabs.append(
            {
                "key": "hstech",
                "title": "恒科",
                "unit": "pct",
                "axis": "hk",
                "points": _clip_curve(
                    _align_pct(hk_tr, hk_axis) if hk_tr else [(t, None) for t in hk_axis], cap
                ),
            }
        )
        for code, info in fund_curves_own.items():
            tabs.append(
                {
                    "key": f"fund:{code}",
                    "title": str(info["label"]),
                    "unit": "pct",
                    "axis": info["axis"],
                    "points": info["points"],
                }
            )
        for info in stock_own:
            tabs.append(
                {
                    "key": f"stock:{info['code']}",
                    "title": str(info["label"]),
                    "unit": "pct",
                    "axis": info["axis"],
                    "points": info["points"],
                }
            )
        # 末点对齐主浮窗当前估值（全持仓、新浪实时），避免分时源/截断分钟造成「现」对不上。
        with self._lock:
            snap = dict(self._snap) if self._snap else {}
        tabs = apply_live_to_tabs(tabs, live_map_from_book(book_from_snap(items, snap)))
        return tabs


    def _curve_sync_live(self) -> None:
        """曲线窗口打开时，用主浮窗最新快照刷新末点和标题数字。"""
        win = getattr(self, "_curve_win", None)
        state = getattr(self, "_curve_state", None)
        if win is None or state is None or state.get("loading"):
            return
        try:
            if not win.winfo_exists():
                return
        except Exception:
            return
        tabs = state.get("tabs") or []
        if not tabs:
            return
        with self._lock:
            items = [dict(x) for x in self._items]
            snap = dict(self._snap) if self._snap else {}
        new_tabs = apply_live_to_tabs(tabs, live_map_from_book(book_from_snap(items, snap)))
        if new_tabs is tabs:
            return
        # 仅当末点变化时重绘，避免无意义刷新
        changed = False
        for a, b in zip(tabs, new_tabs):
            if (a.get("points") or []) != (b.get("points") or []):
                changed = True
                break
        if not changed:
            return
        state["tabs"] = new_tabs
        try:
            self._curve_draw()
        except Exception:
            pass

    def _show_fund_detail(self) -> None:
        """右键：各基金持仓贡献明细（后台拉行情，防闪）。"""

        def work() -> None:
            with self._lock:
                items = [dict(x) for x in self._items]
                states = {c: dict(s) for c, s in self._fund_state.items()}
                snap = dict(self._snap) if self._snap else {}
            funds_out: List[dict] = []
            all_codes: List[str] = []
            for it in items:
                if it.get("kind") == "stock":
                    continue
                code = it["code"]
                st = states.get(code) or {}
                holdings = list(st.get("holdings") or [])
                all_codes.extend(holdings_to_sina_codes(holdings))
            seen = set()
            uniq = []
            for c in all_codes:
                if c not in seen:
                    seen.add(c)
                    uniq.append(c)
            try:
                batch = _sina_batch(uniq) if uniq else {}
            except Exception:
                batch = {}
            fund_snaps = (snap.get("funds") or {}) if snap else {}
            for it in items:
                if it.get("kind") == "stock":
                    continue
                code = it["code"]
                st = states.get(code) or {}
                holdings = list(st.get("holdings") or [])
                rows = holding_contrib_rows(holdings, batch)
                fs = fund_snaps.get(code) or {}
                try:
                    est_pct = float(fs.get("est_pct")) if fs.get("est_pct") is not None else None
                except Exception:
                    est_pct = None
                if est_pct is None and rows:
                    est_pct = sum(r["contrib"] for r in rows)
                funds_out.append(
                    {
                        "code": code,
                        "label": it.get("label") or code,
                        "est_pct": est_pct,
                        "rows": rows,
                    }
                )
            self.root.after(0, lambda: self._fund_detail_dialog(funds_out))

        threading.Thread(target=work, daemon=True).start()

    def _fund_detail_dialog(self, funds: List[dict]) -> None:
        win = tk.Toplevel(self.root)
        win.withdraw()
        win.title("持仓贡献明细")
        win.configure(bg=self.bg)
        win.attributes("-topmost", True)
        win.transient(self.root)
        win.resizable(True, True)

        tip = tk.Label(
            win,
            text="贡献% = (权重%/100) × 个股涨跌%。按贡献升序（最拖累在上）。",
            font=self.font,
            fg=self.fg,
            bg=self.bg,
            justify="left",
            anchor="w",
        )
        tip.pack(fill="x", padx=10, pady=(10, 4))

        wrap = tk.Frame(win, bg=self.bg)
        wrap.pack(fill="both", expand=True, padx=10, pady=4)
        canvas = tk.Canvas(wrap, bg=self.bg, highlightthickness=0, height=360, width=520)
        sb = tk.Scrollbar(wrap, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas, bg=self.bg)
        inner.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        def _wheel(e) -> None:
            if getattr(e, "delta", 0):
                canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
            elif getattr(e, "num", None) == 4:
                canvas.yview_scroll(-1, "units")
            elif getattr(e, "num", None) == 5:
                canvas.yview_scroll(1, "units")

        canvas.bind_all("<MouseWheel>", _wheel)
        canvas.bind_all("<Button-4>", _wheel)
        canvas.bind_all("<Button-5>", _wheel)

        def _on_close() -> None:
            try:
                canvas.unbind_all("<MouseWheel>")
                canvas.unbind_all("<Button-4>")
                canvas.unbind_all("<Button-5>")
            except Exception:
                pass
            win.destroy()

        win.protocol("WM_DELETE_WINDOW", _on_close)

        mono = ("Consolas", 9)

        def _cell(parent, text: str, width: int, *, fg: str, anchor: str = "e") -> None:
            tk.Label(
                parent,
                text=text,
                width=width,
                font=mono,
                fg=fg,
                bg=self.bg,
                anchor=anchor,
            ).pack(side="left")

        if not funds:
            tk.Label(
                inner,
                text="暂无基金持仓。",
                font=self.font,
                fg=self.fg,
                bg=self.bg,
                anchor="w",
            ).pack(fill="x", pady=8)

        for fi, fund in enumerate(funds):
            label = str(fund.get("label") or fund.get("code") or "")
            est = fund.get("est_pct")
            if est is None:
                head = f"{label}"
            else:
                sign = "+" if float(est) > 0 else ""
                head = f"{label}  估值 {sign}{float(est):.2f}%"
            tk.Label(
                inner,
                text=head,
                font=("Segoe UI", 9, "bold"),
                fg="#cccccc",
                bg=self.bg,
                anchor="w",
            ).pack(fill="x", pady=(10 if fi else 2, 2))

            hdr = tk.Frame(inner, bg=self.bg)
            hdr.pack(fill="x")
            for txt, w, anc in (
                ("名称", 12, "w"),
                ("代码", 8, "w"),
                ("权重%", 8, "e"),
                ("涨跌%", 8, "e"),
                ("贡献%", 8, "e"),
            ):
                tk.Label(
                    hdr,
                    text=txt,
                    width=w,
                    font=mono,
                    fg=self.fg,
                    bg=self.bg,
                    anchor=anc,
                ).pack(side="left")

            rows = list(fund.get("rows") or [])
            if not rows:
                tk.Label(
                    inner,
                    text="  （无持仓行情）",
                    font=self.font,
                    fg=self.fg,
                    bg=self.bg,
                    anchor="w",
                ).pack(fill="x")
                continue
            for r in rows:
                row = tk.Frame(inner, bg=self.bg)
                row.pack(fill="x")
                name = (r.get("name") or r.get("code") or "")[:8]
                _cell(row, name, 12, fg=self.fg, anchor="w")
                _cell(row, str(r.get("code") or ""), 8, fg=self.fg, anchor="w")
                _cell(row, f"{float(r['weight']):.2f}", 8, fg=self.fg)
                pct = float(r["pct"])
                _cell(row, f"{pct:+.2f}", 8, fg=self._color(pct))
                contrib = float(r["contrib"])
                _cell(row, f"{contrib:+.2f}", 8, fg=self._color(contrib))

        btn_fr = tk.Frame(win, bg=self.bg)
        btn_fr.pack(fill="x", padx=10, pady=(4, 10))
        tk.Button(btn_fr, text="关闭", command=_on_close).pack(side="right")

        win.update_idletasks()
        need_w, need_h = 560, 480
        sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
        x, y = (sw - need_w) // 2, (sh - need_h) // 2
        x = max(8, min(x, sw - need_w - 8))
        y = max(8, min(y, sh - need_h - 8))
        win.geometry(f"{need_w}x{need_h}+{x}+{y}")
        win.deiconify()
        win.lift()

    def _show_est_errors(self) -> None:
        """弹窗展示近期估值 vs 官方净值误差。"""
        def work() -> None:
            try:
                fill_official_for_log()
            except Exception:
                pass
            rows = read_est_log()
            # 最新日期优先
            rows = sorted(
                rows,
                key=lambda r: (r.get("date") or "", r.get("code") or ""),
                reverse=True,
            )
            self.root.after(0, lambda: self._est_error_dialog(rows))

        threading.Thread(target=work, daemon=True).start()

    def _est_error_dialog(self, rows: List[dict]) -> None:
        win = tk.Toplevel(self.root)
        win.title("估值误差")
        win.configure(bg=self.bg)
        win.transient(self.root)
        tip = tk.Label(
            win,
            text=(
                f"日志：{EST_LOG_PATH.name}（与脚本同目录）\n"
                "「收盘估值」= 当日收盘窗口落盘（A股≈15:05 / 港股≈16:10），与浮窗实时估值可能不同。\n"
                "误差 = 官方 − 收盘估值。估值收益 = 本金×收盘估值%；真实收益 = 本金×官方%。"
            ),
            font=self.font,
            fg=self.fg,
            bg=self.bg,
            justify="left",
            anchor="w",
        )
        tip.pack(fill="x", padx=10, pady=(10, 4))

        wrap = tk.Frame(win, bg=self.bg)
        wrap.pack(fill="both", expand=True, padx=10, pady=4)
        canvas = tk.Canvas(wrap, bg=self.bg, highlightthickness=0, height=280)
        sb = tk.Scrollbar(wrap, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas, bg=self.bg)
        inner.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        hdr = tk.Frame(inner, bg=self.bg)
        hdr.pack(fill="x", pady=(0, 2))
        for txt, w, anc in (
            ("日期", 12, "w"),
            ("标签", 8, "w"),
            ("收盘估值%", 10, "e"),
            ("官方%", 8, "e"),
            ("官方-估值", 10, "e"),
            ("估值收益", 10, "e"),
            ("真实收益", 10, "e"),
            ("收盘估值净值", 12, "e"),
            ("官方净值", 10, "e"),
        ):
            tk.Label(
                hdr,
                text=txt,
                width=w,
                font=("Consolas", 9),
                fg=self.fg,
                bg=self.bg,
                anchor=anc,
            ).pack(side="left")

        show = rows[:40]
        if not show:
            tk.Label(
                inner,
                text="暂无记录。交易日 15:05 后自动写入；也可点「记下当前估值」。",
                font=self.font,
                fg=self.fg,
                bg=self.bg,
                anchor="w",
            ).pack(fill="x", pady=8)
        mono = ("Consolas", 9)
        # 本金：优先当前浮窗持仓，缺则再读 holdings.json
        amt_by_code: Dict[str, float] = {}
        try:
            for it in self._items:
                amt_by_code[str(it.get("code") or "")] = float(it.get("amount") or 0.0)
        except Exception:
            pass
        try:
            for it in load_items():
                c = str(it.get("code") or "")
                if c and c not in amt_by_code:
                    amt_by_code[c] = float(it.get("amount") or 0.0)
                elif c:
                    amt_by_code[c] = float(it.get("amount") or amt_by_code.get(c) or 0.0)
        except Exception:
            pass

        def _cell(parent, text: str, width: int, *, fg: str, anchor: str = "e") -> None:
            tk.Label(
                parent,
                text=text,
                width=width,
                font=mono,
                fg=fg,
                bg=self.bg,
                anchor=anchor,
                justify="left",
            ).pack(side="left")

        def _pnl_cell(pnl: Optional[float], *, pending: bool = False, no_amt: bool = False):
            if no_amt:
                return "—", self.fg
            if pending or pnl is None:
                return "待官方", self.fg
            n = int(round(pnl))
            if n > 0:
                return f"+{n}", self.fg_up
            if n < 0:
                return f"{n}", self.fg_dn
            return "0", self.fg_flat

        # 按日期分组（show 已按日期新→旧），每组末尾插「总计」行
        groups: List[Tuple[str, List[dict]]] = []
        for r in show:
            d = str(r.get("date") or "")
            if not groups or groups[-1][0] != d:
                groups.append((d, [r]))
            else:
                groups[-1][1].append(r)

        for date_s, group in groups:
            day_pnl = 0.0
            day_est_pnl = 0.0
            day_has_official = False
            day_has_est = False
            for r in group:
                try:
                    ep = float(r["est_pct"]) if r.get("est_pct") else None
                except Exception:
                    ep = None
                try:
                    op = float(r["official_pct"]) if r.get("official_pct") else None
                except Exception:
                    op = None
                try:
                    er = float(r["err_pct"]) if r.get("err_pct") else None
                except Exception:
                    er = None
                try:
                    en = float(r["est_nav"]) if r.get("est_nav") else None
                except Exception:
                    en = None
                try:
                    on = float(r["official_nav"]) if r.get("official_nav") else None
                except Exception:
                    on = None
                label = (r.get("label") or r.get("code") or "")[:6]
                if er is None:
                    err_txt, err_fg = "待官方", self.fg
                elif er > 0.0005:
                    err_txt, err_fg = f"{er:+.2f}", self.fg_up
                elif er < -0.0005:
                    err_txt, err_fg = f"{er:+.2f}", self.fg_dn
                else:
                    err_txt, err_fg = f"{er:+.2f}", self.fg_flat

                code = str(r.get("code") or "")
                amount = float(amt_by_code.get(code) or 0.0)
                if amount <= 0:
                    est_pnl_txt, est_pnl_fg = _pnl_cell(None, no_amt=True)
                    pnl_txt, pnl_fg = _pnl_cell(None, no_amt=True)
                else:
                    if ep is None:
                        est_pnl_txt, est_pnl_fg = "—", self.fg
                    else:
                        est_pnl = amount * ep / 100.0
                        day_est_pnl += est_pnl
                        day_has_est = True
                        est_pnl_txt, est_pnl_fg = _pnl_cell(est_pnl)
                    if op is None:
                        pnl_txt, pnl_fg = _pnl_cell(None, pending=True)
                    else:
                        pnl = amount * op / 100.0
                        day_pnl += pnl
                        day_has_official = True
                        pnl_txt, pnl_fg = _pnl_cell(pnl)

                row = tk.Frame(inner, bg=self.bg)
                row.pack(fill="x")
                _cell(row, date_s, 12, fg=self.fg, anchor="w")
                _cell(row, label, 8, fg=self.fg, anchor="w")
                _cell(row, "—" if ep is None else f"{ep:+.2f}", 10, fg=self.fg)
                _cell(row, "—" if op is None else f"{op:+.2f}", 8, fg=self.fg)
                _cell(row, err_txt, 10, fg=err_fg)
                _cell(row, est_pnl_txt, 10, fg=est_pnl_fg)
                _cell(row, pnl_txt, 10, fg=pnl_fg)
                _cell(row, "—" if en is None else f"{en:.4f}", 12, fg=self.fg)
                _cell(row, "—" if on is None else f"{on:.4f}", 10, fg=self.fg)

            # 当日总计：估值收益 + 真实收益合计
            if day_has_est:
                est_tot_txt, est_tot_fg = _pnl_cell(day_est_pnl)
            else:
                est_tot_txt, est_tot_fg = "—", self.fg
            if day_has_official:
                tot_txt, tot_fg = _pnl_cell(day_pnl)
            else:
                tot_txt, tot_fg = _pnl_cell(None, pending=True)
            tot = tk.Frame(inner, bg=self.bg)
            tot.pack(fill="x", pady=(0, 4))
            _cell(tot, date_s, 12, fg=self.fg, anchor="w")
            _cell(tot, "总计", 8, fg=self.fg, anchor="w")
            _cell(tot, "—", 10, fg=self.fg)
            _cell(tot, "—", 8, fg=self.fg)
            _cell(tot, "—", 10, fg=self.fg)
            _cell(tot, est_tot_txt, 10, fg=est_tot_fg)
            _cell(tot, tot_txt, 10, fg=tot_fg)
            _cell(tot, "—", 12, fg=self.fg)
            _cell(tot, "—", 10, fg=self.fg)

        btn_fr = tk.Frame(win, bg=self.bg)
        btn_fr.pack(fill="x", padx=10, pady=(4, 10))

        def do_fill() -> None:
            def work() -> None:
                n = 0
                try:
                    n = fill_official_for_log()
                except Exception:
                    n = 0
                rows2 = read_est_log()
                rows2 = sorted(
                    rows2,
                    key=lambda r: (r.get("date") or "", r.get("code") or ""),
                    reverse=True,
                )
                self.root.after(0, lambda: (win.destroy(), self._est_error_dialog(rows2),
                                            messagebox.showinfo("回填", f"新回填 {n} 条", parent=self.root)))

            threading.Thread(target=work, daemon=True).start()

        def do_snap_now() -> None:
            def work() -> None:
                with self._lock:
                    snap = dict(self._snap)
                    items = [dict(x) for x in self._items]
                    states = {c: dict(s) for c, s in self._fund_state.items()}
                funds = snap.get("funds") or {}
                # 任意时刻可补记「今日尚未写入」的基金；已有同行不覆盖
                n = self._maybe_log_close_estimates(
                    items, funds, states, force=False, ignore_window=True
                )
                try:
                    fill_official_for_log()
                except Exception:
                    pass
                rows2 = read_est_log()
                rows2 = sorted(
                    rows2,
                    key=lambda r: (r.get("date") or "", r.get("code") or ""),
                    reverse=True,
                )
                self.root.after(
                    0,
                    lambda: (
                        win.destroy(),
                        self._est_error_dialog(rows2),
                        messagebox.showinfo("记录", f"写入/保留 {n} 条（同日已有则不覆盖）", parent=self.root),
                    ),
                )

            threading.Thread(target=work, daemon=True).start()

        def open_csv() -> None:
            try:
                _ensure_est_log()
                import os
                os.startfile(str(EST_LOG_PATH))  # type: ignore[attr-defined]
            except Exception as e:
                messagebox.showerror("打开失败", str(e), parent=win)

        tk.Button(btn_fr, text="回填官方净值", command=do_fill).pack(side="left", padx=(0, 6))
        tk.Button(btn_fr, text="记下当前估值", command=do_snap_now).pack(side="left", padx=(0, 6))
        tk.Button(btn_fr, text="打开 CSV", command=open_csv).pack(side="left", padx=(0, 6))
        tk.Button(btn_fr, text="关闭", command=win.destroy).pack(side="right")

        win.update_idletasks()
        w, h = 820, 420
        sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
        x, y = (sw - w) // 2, (sh - h) // 2
        win.geometry(f"{w}x{h}+{x}+{y}")
        win.lift()

    def quit(self) -> None:
        self._stop = True
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    FloatWidget().run()


if __name__ == "__main__":
    main()
