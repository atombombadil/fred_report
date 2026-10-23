#!/usr/bin/env python3
"""
FRED Steel & Auto Production Report
Fetches US steel and automobile production data from the FRED API,
steel import data from the Census Bureau API,
generates an HTML report with inline charts, and emails it via Gmail.
"""

import argparse
import os
import sys
import smtplib
import base64
import webbrowser
from collections import defaultdict
from io import BytesIO
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage

import requests
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from dotenv import load_dotenv

load_dotenv()

FRED_API_KEY = os.environ.get("FRED_API_KEY")
CENSUS_API_KEY = os.environ.get("CENSUS_API_KEY")
GMAIL_ADDRESS = os.environ.get("GMAIL_ADDRESS")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")
REPORT_RECIPIENT = os.environ.get("REPORT_RECIPIENT")

# --- FRED series ---
SERIES = {
    "IPG3311A2S": {
        "name": "US Steel Production",
        "units": "Index (2017=100)",
        "description": "Industrial Production: Iron and Steel Products",
    },
    "TOTALSA": {
        "name": "US Total Vehicle Sales",
        "units": "Millions of Units (SAAR)",
        "description": "Total Vehicle Sales, Seasonally Adjusted Annual Rate",
    },
}

CAPACITY_UTIL_SERIES = {
    "CAPUTLG3311A2S": {"name": "Iron & Steel Products", "naics": "3311,2"},
    "CAPUTLG332S": {"name": "Fabricated Metal Products", "naics": "332"},
    "CAPUTLG333S": {"name": "Machinery", "naics": "333"},
    "CAPUTLG335S": {"name": "Electrical Equipment & Components", "naics": "335"},
    "CAPUTLG336S": {"name": "Transportation Equipment", "naics": "336"},
}

FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"

# --- Census steel import config ---
CENSUS_BASE = "https://api.census.gov/data/timeseries/intltrade/imports/hs"

IMPORT_SERIES = [
    # ── Group 23: Reinforcing Bars ─────────────────────────────
    {
        "name": "Group 23 — Reinforcing Bars",
        "hs10_codes": ["7213100000", "7214200000", "7228308010"],
        "countries": [
            {"code": "-", "name": "Total"},
            {"code": "5520", "name": "Vietnam"},
            {"code": "7290", "name": "Egypt"},
            {"code": "4890", "name": "Turkey"},
            {"code": "5800", "name": "South Korea"},
        ],
    },
    # ── Groups 9+21: Structural Shapes ────────────────────────
    {
        "name": "Groups 9+21 — Structural Shapes",
        "hs10_codes": [
            # Group 21: Light Shaped Bars
            "7216100010", "7216100050", "7216210000", "7216220000",
            "7228703060", "7228703081",
            # Group 9: Heavy Structural Shapes
            "7216310000", "7216320000", "7216330030", "7216330060",
            "7216330090", "7216400010", "7216400050", "7216500000",
            "7216990010", "7216990090",
            "7228703010", "7228703020", "7228703041", "7228706000",
        ],
        "countries": [
            {"code": "-", "name": "Total"},
            {"code": "2010", "name": "Mexico"},
            {"code": "5800", "name": "South Korea"},
            {"code": "5330", "name": "India"},
            {"code": "1220", "name": "Canada"},
            {"code": "0003", "name": "EU"},
            {"code": "4890", "name": "Turkey"},
        ],
    },
    # ── Group 14: Plates in Coils ──────────────────────────────
    {
        "name": "Group 14 — Plates in Coils",
        "hs10_codes": [
            "7208101500", "7208103000",
            "7208253000", "7208256000",
            "7208360030", "7208360060",
            "7208370030", "7208370060",
            "7211140090",
            "7225303005", "7225303050",
        ],
        "countries": [
            {"code": "-", "name": "Total"},
            {"code": "5800", "name": "South Korea"},
            {"code": "3510", "name": "Brazil"},
            {"code": "1220", "name": "Canada"},
            {"code": "5880", "name": "Japan"},
            {"code": "4280", "name": "Germany"},
            {"code": "4890", "name": "Turkey"},
        ],
    },
    # ── Group 46: Hot Rolled Sheets ───────────────────────────
    {
        "name": "Group 46 — Hot Rolled Sheets",
        "hs10_codes": [
            "7208106000",
            "7208260030", "7208260060",
            "7208270040", "7208270045", "7208270060",
            "7208380015", "7208380030", "7208380090",
            "7208390020", "7208390025", "7208390030", "7208390090",
            "7208406030", "7208406060",
            "7208530000", "7208540000",
            "7208900000",
            "7225307000", "7225407000",
        ],
        "countries": [
            {"code": "-", "name": "Total"},
            {"code": "5800", "name": "South Korea"},
            {"code": "3510", "name": "Brazil"},
            {"code": "1220", "name": "Canada"},
            {"code": "5880", "name": "Japan"},
            {"code": "4280", "name": "Germany"},
            {"code": "4890", "name": "Turkey"},
        ],
    },
    # ── Group 12: Cut to Length Plate ─────────────────────────
    {
        "name": "Group 12 — Cut to Length Plate",
        "hs10_codes": [
            "7208403030", "7208403060",
            "7208510030", "7208510045", "7208510060",
            "7208520000",
            "7210901000",
            "7211130000", "7211140030", "7211140045",
            "7225403005", "7225403050",
            "7225506000", "7226915000",
        ],
        "countries": [
            {"code": "-", "name": "Total"},
            {"code": "5800", "name": "South Korea"},
            {"code": "1220", "name": "Canada"},
            {"code": "5880", "name": "Japan"},
            {"code": "2010", "name": "Mexico"},
            {"code": "4279", "name": "France"},
            {"code": "4890", "name": "Turkey"},
        ],
    },
    # ── Group 48: Cold Rolled Sheets ──────────────────────────
    {
        "name": "Group 48 — Cold Rolled Sheets",
        "hs10_codes": [
            "7209150000",
            "7209160040", "7209160045", "7209160060", "7209160070", "7209160091",
            "7209170040", "7209170045", "7209170060", "7209170070", "7209170091",
            "7209181530", "7209181560",
            "7209186020", "7209186090",
            "7209250000", "7209260000", "7209270000", "7209280000",
            "7209900000",
            "7210703000",
            "7225507000", "7225508010", "7225508080",
            "7225990010", "7225990090",
        ],
        "countries": [
            {"code": "-", "name": "Total"},
            {"code": "5800", "name": "South Korea"},
            {"code": "5880", "name": "Japan"},
            {"code": "4280", "name": "Germany"},
            {"code": "5830", "name": "Taiwan"},
            {"code": "2010", "name": "Mexico"},
            {"code": "4890", "name": "Turkey"},
        ],
    },
    # ── Group 50: Galvanized Hot-Dipped Sheets ────────────────
    {
        "name": "Group 50 — Galvanized Hot-Dipped Sheets",
        "hs10_codes": [
            "7210410000",
            "7210490040", "7210490045", "7210490091", "7210490095",
            "7210706060",
            "7212301030", "7212301090", "7212303000", "7212305000",
            "7225920000", "7226990130",
        ],
        "countries": [
            {"code": "-", "name": "Total"},
            {"code": "1220", "name": "Canada"},
            {"code": "5800", "name": "South Korea"},
            {"code": "5830", "name": "Taiwan"},
            {"code": "3510", "name": "Brazil"},
            {"code": "2010", "name": "Mexico"},
            {"code": "4890", "name": "Turkey"},
        ],
    },
    # ── Group 7: Wire Rod ─────────────────────────────────────
    {
        "name": "Group 7 — Wire Rod",
        "hs10_codes": [
            "7213913011", "7213913015", "7213913020", "7213913093",
            "7213914500", "7213916000",
            "7213990030", "7213990090",
            "7227200030",
            "7227906020", "7227906030", "7227906035",
        ],
        "countries": [
            {"code": "-", "name": "Total"},
            {"code": "1220", "name": "Canada"},
            {"code": "2010", "name": "Mexico"},
            {"code": "4890", "name": "Turkey"},
            {"code": "4840", "name": "Greece"},
            {"code": "7290", "name": "Egypt"},
        ],
    },
    # ── Group 19: Hot Rolled Bars ─────────────────────────────
    {
        "name": "Group 19 — Hot Rolled Bars",
        "hs10_codes": [
            "7213200010", "7213200080",
            "7213990060",
            "7214100000",
            "7214300010", "7214300080",
            "7214910016", "7214910020", "7214910060", "7214910090",
            "7214990016", "7214990021", "7214990026",
            "7214990031", "7214990036", "7214990040", "7214990045",
            "7214990060", "7214990075", "7214990090",
            "7215901000",
            "7227200080",
            "7227906005", "7227906010", "7227906040", "7227906090",
            "7228201000",
            "7228308005", "7228308015", "7228308041", "7228308045", "7228308070",
            "7228400000", "7228606000", "7228800000",
        ],
        "countries": [
            {"code": "-", "name": "Total"},
            {"code": "4890", "name": "Turkey"},
            {"code": "2010", "name": "Mexico"},
            {"code": "1220", "name": "Canada"},
            {"code": "5800", "name": "South Korea"},
            {"code": "5330", "name": "India"},
        ],
    },
]


def fetch_series(series_id: str) -> list[dict]:
    """Fetch all observations for a FRED series."""
    resp = requests.get(
        FRED_BASE,
        params={
            "series_id": series_id,
            "api_key": FRED_API_KEY,
            "file_type": "json",
        },
        timeout=30,
    )
    resp.raise_for_status()
    observations = resp.json()["observations"]
    result = []
    for obs in observations:
        if obs["value"] == ".":
            continue
        result.append({
            "date": datetime.strptime(obs["date"], "%Y-%m-%d"),
            "value": float(obs["value"]),
        })
    return result


def compute_metrics(data: list[dict]) -> dict:
    """Compute latest, MoM, YoY, all-time peak, and 10-year peak metrics."""
    if len(data) < 2:
        raise ValueError("Not enough data to compute metrics")

    latest = data[-1]
    prev_month = data[-2]

    target_yoy = latest["date"] - timedelta(days=365)
    prev_year = min(data, key=lambda d: abs((d["date"] - target_yoy).days))

    peak = max(data, key=lambda d: d["value"])

    ten_year_cutoff = latest["date"] - timedelta(days=10 * 365)
    ten_year_data = [d for d in data if d["date"] >= ten_year_cutoff]
    peak_10y = max(ten_year_data, key=lambda d: d["value"])

    mom_change = ((latest["value"] - prev_month["value"]) / prev_month["value"]) * 100
    yoy_change = ((latest["value"] - prev_year["value"]) / prev_year["value"]) * 100
    off_peak = ((latest["value"] - peak["value"]) / peak["value"]) * 100
    off_peak_10y = ((latest["value"] - peak_10y["value"]) / peak_10y["value"]) * 100

    return {
        "latest_date": latest["date"],
        "latest_value": latest["value"],
        "prev_month_value": prev_month["value"],
        "mom_change": mom_change,
        "prev_year_date": prev_year["date"],
        "prev_year_value": prev_year["value"],
        "yoy_change": yoy_change,
        "peak_value": peak["value"],
        "peak_date": peak["date"],
        "off_peak": off_peak,
        "peak_10y_value": peak_10y["value"],
        "peak_10y_date": peak_10y["date"],
        "off_peak_10y": off_peak_10y,
    }


def compute_yoy_pct_change(data: list[dict]) -> list[dict]:
    """Compute year-over-year percent change for each observation."""
    by_ym = {}
    for d in data:
        by_ym[(d["date"].year, d["date"].month)] = d["value"]
    result = []
    for d in data:
        prev_key = (d["date"].year - 1, d["date"].month)
        if prev_key in by_ym and by_ym[prev_key] != 0:
            pct = ((d["value"] - by_ym[prev_key]) / by_ym[prev_key]) * 100
            result.append({"date": d["date"], "value": pct})
    return result


# ──────────────────────────────────────────────────────────────
# Census steel imports
# ──────────────────────────────────────────────────────────────

def _census_time_range(n_years: int = 3) -> tuple[str, str]:
    """Return (start, end) time strings for the Census API `from...to` syntax."""
    now = datetime.now()
    start = f"{now.year - n_years}-01"
    # Last complete month
    if now.month == 1:
        end = f"{now.year - 1}-12"
    else:
        end = f"{now.year}-{now.month - 1:02d}"
    return start, end


def _fetch_hs10_bulk(hs10_code: str, time_start: str, time_end: str) -> list[list]:
    """Fetch all countries × all months for one HS10 code in a single call."""
    params = {
        "get": "I_COMMODITY,CTY_CODE,GEN_QY1_MO",
        "I_COMMODITY": hs10_code,
        "time": f"from {time_start} to {time_end}",
        "key": CENSUS_API_KEY,
    }
    resp = requests.get(CENSUS_BASE, params=params, timeout=60)
    resp.raise_for_status()
    return resp.json()


def fetch_import_raw(import_cfg: dict) -> dict:
    """
    Fetch raw monthly import data for one HS code group.
    Returns {country_code: {(year, month): qty_kg}} for all countries
    listed in the config PLUS the total ("-").
    """
    time_start, time_end = _census_time_range(3)
    country_codes = {c["code"] for c in import_cfg["countries"]} | {"-"}

    accum = defaultdict(lambda: defaultdict(int))

    for hs10 in import_cfg["hs10_codes"]:
        print(f"      Fetching {hs10}...")
        try:
            data = _fetch_hs10_bulk(hs10, time_start, time_end)
        except Exception as e:
            print(f"        Warning: {e}")
            continue

        if len(data) < 2:
            continue

        for row in data[1:]:
            cty_code = row[1]
            qty_str = row[2]
            time_str = row[-1]

            if cty_code not in country_codes:
                continue

            qty = int(qty_str) if qty_str and qty_str not in ("0", "") else 0
            year, month = int(time_str.split("-")[0]), int(time_str.split("-")[1])
            accum[cty_code][(year, month)] += qty

    return accum


def build_import_table_data(import_cfg: dict, accum: dict) -> dict:
    """
    Organize pre-fetched raw data into annual totals with YoY changes.
    Shows full-year totals for complete years and YTD for the latest year.
    YoY comparisons use the same month range for apples-to-apples accuracy.
    """
    all_ym = set()
    for monthly in accum.values():
        all_ym.update(monthly.keys())
    if not all_ym:
        return {"name": import_cfg["name"], "years": [], "year_labels": {},
                "countries": []}

    years = sorted(set(ym[0] for ym in all_ym))
    latest_year = years[-1]
    ytd_max_month = max(ym[1] for ym in all_ym if ym[0] == latest_year)

    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                   "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    year_labels = {}
    for y in years:
        if y == latest_year and ytd_max_month < 12:
            year_labels[y] = f"{y} YTD (Jan\u2013{month_names[ytd_max_month - 1]})"
        else:
            year_labels[y] = str(y)

    country_data = []
    for ctry in import_cfg["countries"]:
        monthly = accum.get(ctry["code"], {})

        annual = {}
        for y in years:
            year_months = [(y, m) for m in range(1, 13) if (y, m) in monthly]
            if year_months:
                total_kg = sum(monthly[ym] for ym in year_months)
                annual[y] = total_kg / 1000
            else:
                annual[y] = None

        yoy = {}
        for i, y in enumerate(years):
            if i == 0:
                yoy[y] = None
                continue

            prev_y = years[i - 1]
            if y == latest_year and ytd_max_month < 12:
                max_m = ytd_max_month
            else:
                max_m = 12

            curr_total = sum(monthly.get((y, m), 0) for m in range(1, max_m + 1))
            prev_total = sum(monthly.get((prev_y, m), 0) for m in range(1, max_m + 1))

            if prev_total > 0:
                yoy[y] = ((curr_total - prev_total) / prev_total) * 100
            else:
                yoy[y] = None

        country_data.append({
            "name": ctry["name"],
            "annual": annual,
            "yoy": yoy,
        })

    return {
        "name": import_cfg["name"],
        "years": years,
        "year_labels": year_labels,
        "countries": country_data,
    }


COUNTRY_COLORS = {
    "South Korea": "#1f77b4",
    "Turkey":      "#d62728",
    "Mexico":      "#ff7f0e",
    "Canada":      "#2ca02c",
    "Japan":       "#9467bd",
    "Germany":     "#8c564b",
    "Brazil":      "#e377c2",
    "India":       "#17becf",
    "Taiwan":      "#bcbd22",
    "EU":          "#7f7f7f",
    "Vietnam":     "#aec7e8",
    "Egypt":       "#ffbb78",
    "France":      "#98df8a",
    "Greece":      "#ff9896",
}
_FALLBACK_COLORS = ["#c5b0d5", "#c49c94", "#f7b6d2", "#dbdb8d", "#9edae5", "#ad494a"]


def make_import_stacked_chart(import_cfg: dict, accum: dict) -> bytes:
    """Generate a stacked bar chart of monthly imports by country (last 24 months)."""
    # Get named countries (excluding Total)
    named_countries = [c for c in import_cfg["countries"] if c["code"] != "-"]
    country_codes = {c["code"]: c["name"] for c in named_countries}

    # Convert to metric tons
    total_monthly = {ym: v / 1000 for ym, v in accum.get("-", {}).items()}
    named_monthly = {}
    for code, name in country_codes.items():
        named_monthly[name] = {ym: v / 1000 for ym, v in accum.get(code, {}).items()}

    # Last 24 months
    all_months = sorted(total_monthly.keys())
    all_months = all_months[-24:]

    dates = [datetime(y, m, 15) for y, m in all_months]
    totals = [total_monthly.get(ym, 0) for ym in all_months]

    country_names = list(named_monthly.keys())
    country_vals = {}
    for name in country_names:
        country_vals[name] = [named_monthly[name].get(ym, 0) for ym in all_months]

    row_sum = [sum(country_vals[n][i] for n in country_names) for i in range(len(all_months))]
    row_rest = [max(0, totals[i] - row_sum[i]) for i in range(len(all_months))]

    fig, ax = plt.subplots(figsize=(10, 4.5))
    bar_width = 20

    fallback_idx = 0
    bottom = [0.0] * len(dates)
    for name in country_names:
        if name in COUNTRY_COLORS:
            color = COUNTRY_COLORS[name]
        else:
            color = _FALLBACK_COLORS[fallback_idx % len(_FALLBACK_COLORS)]
            fallback_idx += 1
        vals = country_vals[name]
        ax.bar(dates, vals, width=bar_width, bottom=bottom,
               label=name, color=color, alpha=0.9)
        bottom = [b + v for b, v in zip(bottom, vals)]

    ax.bar(dates, row_rest, width=bar_width, bottom=bottom,
           label="Rest of World", color="#cccccc", alpha=0.7)

    # 12-month trailing average line
    last_12 = all_months[-12:]
    avg_12 = sum(total_monthly.get(ym, 0) for ym in last_12) / len(last_12)
    ax.axhline(y=avg_12, color="#333", linewidth=1.2, linestyle="--", alpha=0.7)
    ax.text(dates[-1] + timedelta(days=8), avg_12,
            f"12-mo avg\n{avg_12:,.0f}",
            fontsize=7.5, color="#333", va="center")

    ax.set_title(f"{import_cfg['name']} — Monthly Imports (Metric Tons)",
                 fontsize=13, fontweight="bold", pad=10)
    ax.set_ylabel("Metric Tons", fontsize=10)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    plt.xticks(rotation=45, fontsize=8)
    plt.yticks(fontsize=9)
    ax.grid(True, alpha=0.3, axis="y")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.legend(loc="upper left", fontsize=8, framealpha=0.9)
    fig.tight_layout()

    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=150)
    plt.close(fig)
    buf.seek(0)
    return buf.read()


# ──────────────────────────────────────────────────────────────
# Charts
# ──────────────────────────────────────────────────────────────

def make_chart(data: list[dict], series_info: dict, metrics: dict) -> bytes:
    """Generate a line chart PNG for the last 4 years with peaks annotated."""
    cutoff = datetime.now() - timedelta(days=4 * 365)
    recent = [d for d in data if d["date"] >= cutoff]

    dates = [d["date"] for d in recent]
    values = [d["value"] for d in recent]

    fig, ax = plt.subplots(figsize=(9, 4))
    ax.plot(dates, values, color="#1f77b4", linewidth=1.8)
    ax.fill_between(dates, values, alpha=0.08, color="#1f77b4")

    if metrics["peak_date"] >= cutoff:
        ax.annotate(
            f"All-Time Peak: {metrics['peak_value']:.1f}\n({metrics['peak_date'].strftime('%b %Y')})",
            xy=(metrics["peak_date"], metrics["peak_value"]),
            xytext=(0, 18), textcoords="offset points", ha="center",
            fontsize=8, color="#d62728",
            arrowprops=dict(arrowstyle="->", color="#d62728", lw=1),
        )

    if (metrics["peak_10y_date"] != metrics["peak_date"]
            and metrics["peak_10y_date"] >= cutoff):
        ax.annotate(
            f"10Y Peak: {metrics['peak_10y_value']:.1f}\n({metrics['peak_10y_date'].strftime('%b %Y')})",
            xy=(metrics["peak_10y_date"], metrics["peak_10y_value"]),
            xytext=(0, 18), textcoords="offset points", ha="center",
            fontsize=8, color="#e65100",
            arrowprops=dict(arrowstyle="->", color="#e65100", lw=1),
        )

    ax.annotate(
        f"{metrics['latest_value']:.1f}",
        xy=(metrics["latest_date"], metrics["latest_value"]),
        xytext=(5, 5), textcoords="offset points",
        fontsize=9, fontweight="bold", color="#1f77b4",
    )

    ax.set_title(series_info["name"], fontsize=13, fontweight="bold", pad=10)
    ax.set_ylabel(series_info["units"], fontsize=10)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=6))
    plt.xticks(rotation=45, fontsize=8)
    plt.yticks(fontsize=9)
    ax.grid(True, alpha=0.3)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()

    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=150)
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def make_yoy_chart(data: list[dict], series_info: dict) -> bytes:
    """Generate a YoY percent change bar chart for the last 4 years."""
    yoy_data = compute_yoy_pct_change(data)
    cutoff = datetime.now() - timedelta(days=4 * 365)
    recent = [d for d in yoy_data if d["date"] >= cutoff]

    dates = [d["date"] for d in recent]
    values = [d["value"] for d in recent]
    colors = ["#2e7d32" if v >= 0 else "#c62828" for v in values]

    fig, ax = plt.subplots(figsize=(9, 3.5))
    ax.bar(dates, values, color=colors, width=25, alpha=0.85)
    ax.axhline(y=0, color="#333", linewidth=0.8)

    ax.set_title(f"{series_info['name']} — Year-over-Year % Change",
                 fontsize=13, fontweight="bold", pad=10)
    ax.set_ylabel("YoY Change (%)", fontsize=10)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=6))
    plt.xticks(rotation=45, fontsize=8)
    plt.yticks(fontsize=9)
    ax.grid(True, alpha=0.3, axis="y")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()

    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=150)
    plt.close(fig)
    buf.seek(0)
    return buf.read()


# ──────────────────────────────────────────────────────────────
# Formatting helpers
# ──────────────────────────────────────────────────────────────

def format_change(val: float) -> str:
    color = "#2e7d32" if val >= 0 else "#c62828"
    arrow = "&#9650;" if val >= 0 else "&#9660;"
    return f'<span style="color:{color};font-weight:bold">{arrow} {val:+.2f}%</span>'


def format_pp_change(val: float) -> str:
    color = "#2e7d32" if val >= 0 else "#c62828"
    arrow = "&#9650;" if val >= 0 else "&#9660;"
    return f'<span style="color:{color};font-weight:bold">{arrow} {val:+.1f} pp</span>'


def format_cap_util(val: float) -> str:
    if val >= 80:
        color = "#2e7d32"
    elif val >= 70:
        color = "#e65100"
    else:
        color = "#c62828"
    return f'<span style="color:{color};font-weight:bold">{val:.1f}%</span>'


def format_tons(val) -> str:
    """Format metric tons with comma separator."""
    if val is None or val == 0:
        return '<span style="color:#999">&mdash;</span>'
    return f"{val:,.0f}"


def _img_src(png_bytes: bytes, cid: str, preview: bool) -> str:
    if preview:
        b64 = base64.b64encode(png_bytes).decode()
        return f"data:image/png;base64,{b64}"
    return f"cid:{cid}"


# ──────────────────────────────────────────────────────────────
# HTML report
# ──────────────────────────────────────────────────────────────

def build_html(results: list[dict], cap_util_data: list[dict],
               import_tables: list[dict], import_charts: list[tuple[str, bytes]] = None,
               preview: bool = False) -> tuple[str, list[tuple[str, bytes]]]:
    """Build the HTML report."""
    now = datetime.now().strftime("%B %d, %Y")
    images = []

    # --- Production summary table ---
    rows_html = ""
    charts_html = ""
    img_idx = 0
    for r in results:
        m = r["metrics"]
        info = r["info"]

        cid_level = f"chart{img_idx}"
        images.append((cid_level, r["chart_png"]))
        img_idx += 1

        cid_yoy = f"chart{img_idx}"
        images.append((cid_yoy, r["yoy_chart_png"]))
        img_idx += 1

        rows_html += f"""
        <tr>
            <td style="padding:10px 14px;font-weight:bold">{info['name']}</td>
            <td style="padding:10px 14px;text-align:right">{m['latest_value']:.1f} <span style="font-size:0.8em;color:#666">{info['units']}</span></td>
            <td style="padding:10px 14px;text-align:center">{format_change(m['mom_change'])}</td>
            <td style="padding:10px 14px;text-align:center">{format_change(m['yoy_change'])}</td>
            <td style="padding:10px 14px;text-align:right">{m['peak_10y_value']:.1f} <span style="font-size:0.8em;color:#666">({m['peak_10y_date'].strftime('%b %Y')})</span></td>
            <td style="padding:10px 14px;text-align:center">{format_change(m['off_peak_10y'])}</td>
            <td style="padding:10px 14px;text-align:right">{m['peak_value']:.1f} <span style="font-size:0.8em;color:#666">({m['peak_date'].strftime('%b %Y')})</span></td>
            <td style="padding:10px 14px;text-align:center">{format_change(m['off_peak'])}</td>
        </tr>"""

        src_level = _img_src(r["chart_png"], cid_level, preview)
        src_yoy = _img_src(r["yoy_chart_png"], cid_yoy, preview)
        charts_html += f"""
        <div style="margin:20px 0">
            <img src="{src_level}" alt="{info['name']} Chart" style="max-width:100%;border-radius:6px;border:1px solid #e0e0e0">
        </div>
        <div style="margin:20px 0">
            <img src="{src_yoy}" alt="{info['name']} YoY Chart" style="max-width:100%;border-radius:6px;border:1px solid #e0e0e0">
        </div>"""

    # --- Capacity utilization table ---
    cap_rows = ""
    for cu in cap_util_data:
        info = cu["info"]
        m = cu["metrics"]
        cap_rows += f"""
        <tr>
            <td style="padding:10px 14px;font-weight:bold">{info['name']}</td>
            <td style="padding:10px 14px;text-align:center;font-size:0.8em;color:#666">NAICS {info['naics']}</td>
            <td style="padding:10px 14px;text-align:center">{format_cap_util(m['latest_value'])}</td>
            <td style="padding:10px 14px;text-align:center;font-size:0.85em;color:#666">{m['latest_date'].strftime('%b %Y')}</td>
            <td style="padding:10px 14px;text-align:center">{format_pp_change(m['latest_value'] - m['prev_month_value'])}</td>
            <td style="padding:10px 14px;text-align:center">{format_pp_change(m['latest_value'] - m['prev_year_value'])}</td>
        </tr>"""

    # --- Steel import charts ---
    import_charts_html = ""
    if import_charts:
        for chart_name, chart_png in import_charts:
            cid = f"chart{img_idx}"
            images.append((cid, chart_png))
            img_idx += 1
            src = _img_src(chart_png, cid, preview)
            import_charts_html += f"""
        <div style="margin:20px 0">
            <img src="{src}" alt="{chart_name}" style="max-width:100%;border-radius:6px;border:1px solid #e0e0e0">
        </div>"""

    # --- Steel import tables ---
    import_html = ""
    for tbl in import_tables:
        years = tbl["years"]

        year_labels = tbl.get("year_labels", {y: str(y) for y in years})

        # Build year column headers (year + YoY pairs)
        year_headers = ""
        for y in years:
            label = year_labels.get(y, str(y))
            year_headers += f'<th style="padding:10px 10px;text-align:right;font-size:0.85em;color:#555">{label}</th>'
            if y != years[0]:
                year_headers += f'<th style="padding:10px 10px;text-align:center;font-size:0.85em;color:#555">YoY</th>'

        import_rows = ""
        for ctry in tbl["countries"]:
            is_total = ctry["name"] == "Total"
            weight = "font-weight:bold;" if is_total else ""
            bg = "background:#fafafa;" if is_total else ""

            cells = ""
            for y in years:
                val = ctry["annual"].get(y)
                cells += f'<td style="padding:10px 10px;text-align:right;{weight}{bg}">{format_tons(val)}</td>'
                if y != years[0]:
                    yoy = ctry["yoy"].get(y)
                    if yoy is not None:
                        cells += f'<td style="padding:10px 10px;text-align:center;{bg}">{format_change(yoy)}</td>'
                    else:
                        cells += f'<td style="padding:10px 10px;text-align:center;{bg}"><span style="color:#999">&mdash;</span></td>'

            import_rows += f"""
            <tr>
                <td style="padding:10px 14px;{weight}{bg}">{ctry['name']}</td>
                {cells}
            </tr>"""

        import_html += f"""
        <h3 style="margin-top:20px;font-size:15px;color:#37474f">{tbl['name']}</h3>
        <table style="width:100%;border-collapse:collapse;background:#fff;border-radius:6px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,0.1);margin-bottom:16px">
            <thead>
                <tr style="background:#f5f5f5">
                    <th style="padding:10px 14px;text-align:left;font-size:0.85em;color:#555">Country</th>
                    {year_headers}
                </tr>
            </thead>
            <tbody>
                {import_rows}
            </tbody>
        </table>"""

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;max-width:800px;margin:0 auto;padding:20px;color:#333">

    <div style="background:linear-gradient(135deg,#1a237e,#283593);padding:24px 30px;border-radius:8px;margin-bottom:24px">
        <h1 style="color:#fff;margin:0;font-size:22px">US Steel &amp; Auto Report</h1>
        <p style="color:#90caf9;margin:6px 0 0;font-size:14px">Production, Vehicle Sales, Capacity Utilization &amp; Steel Imports &mdash; {now}</p>
    </div>

    <h2 style="font-size:18px;color:#1a237e;margin-bottom:12px">Production Summary</h2>
    <table style="width:100%;border-collapse:collapse;background:#fff;border-radius:6px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,0.1)">
        <thead>
            <tr style="background:#f5f5f5">
                <th style="padding:10px 14px;text-align:left;font-size:0.85em;color:#555">Indicator</th>
                <th style="padding:10px 14px;text-align:right;font-size:0.85em;color:#555">Latest</th>
                <th style="padding:10px 14px;text-align:center;font-size:0.85em;color:#555">MoM</th>
                <th style="padding:10px 14px;text-align:center;font-size:0.85em;color:#555">YoY</th>
                <th style="padding:10px 14px;text-align:right;font-size:0.85em;color:#555">10-Year Peak</th>
                <th style="padding:10px 14px;text-align:center;font-size:0.85em;color:#555">vs 10Y Peak</th>
                <th style="padding:10px 14px;text-align:right;font-size:0.85em;color:#555">All-Time Peak</th>
                <th style="padding:10px 14px;text-align:center;font-size:0.85em;color:#555">vs AT Peak</th>
            </tr>
        </thead>
        <tbody>
            {rows_html}
        </tbody>
    </table>

    <h2 style="margin-top:30px;font-size:18px;color:#1a237e">4-Year Trends</h2>
    {charts_html}

    <h2 style="margin-top:30px;font-size:18px;color:#1a237e">Capacity Utilization</h2>
    <table style="width:100%;border-collapse:collapse;background:#fff;border-radius:6px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,0.1)">
        <thead>
            <tr style="background:#f5f5f5">
                <th style="padding:10px 14px;text-align:left;font-size:0.85em;color:#555">Industry</th>
                <th style="padding:10px 14px;text-align:center;font-size:0.85em;color:#555">NAICS</th>
                <th style="padding:10px 14px;text-align:center;font-size:0.85em;color:#555">Utilization</th>
                <th style="padding:10px 14px;text-align:center;font-size:0.85em;color:#555">As Of</th>
                <th style="padding:10px 14px;text-align:center;font-size:0.85em;color:#555">MoM (pp)</th>
                <th style="padding:10px 14px;text-align:center;font-size:0.85em;color:#555">YoY (pp)</th>
            </tr>
        </thead>
        <tbody>
            {cap_rows}
        </tbody>
    </table>

    <h2 style="margin-top:30px;font-size:18px;color:#1a237e">Steel Imports by Volume</h2>
    {import_charts_html}
    <p style="font-size:0.85em;color:#666;margin-bottom:4px">Annual totals in metric tons (source: US Census Bureau)</p>
    {import_html}

    <div style="margin-top:30px;padding-top:16px;border-top:1px solid #e0e0e0;font-size:0.8em;color:#999">
        <p>Production data: FRED (Federal Reserve Bank of St. Louis) &mdash; IPG3311A2S, TOTALSA</p>
        <p>Capacity Utilization: FRED &mdash; CAPUTLG3311A2S, CAPUTLG332S, CAPUTLG333S, CAPUTLG335S, CAPUTLG336S</p>
        <p>Import data: US Census Bureau International Trade API &mdash; HS 721420, HS 7216</p>
        <p>Report generated {now}</p>
    </div>

</body>
</html>"""

    return html, images


def send_email(html: str, images: list[tuple[str, bytes]]):
    """Send the HTML report via Gmail SMTP with inline images."""
    msg = MIMEMultipart("related")
    msg["Subject"] = f"US Steel & Auto Report — {datetime.now().strftime('%B %Y')}"
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = REPORT_RECIPIENT

    msg.attach(MIMEText(html, "html"))

    for cid, png_data in images:
        img = MIMEImage(png_data, _subtype="png")
        img.add_header("Content-ID", f"<{cid}>")
        img.add_header("Content-Disposition", "inline", filename=f"{cid}.png")
        msg.attach(img)

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_ADDRESS, REPORT_RECIPIENT, msg.as_string())


def main():
    parser = argparse.ArgumentParser(description="FRED Production Report")
    parser.add_argument("--preview", action="store_true",
                        help="Open report in browser instead of emailing")
    parser.add_argument("--out-file", metavar="PATH",
                        help="Also save HTML to this file (in addition to emailing)")
    args = parser.parse_args()

    # Validate config
    required_vars = ["FRED_API_KEY", "CENSUS_API_KEY"]
    if not args.preview:
        required_vars += ["GMAIL_ADDRESS", "GMAIL_APP_PASSWORD", "REPORT_RECIPIENT"]
    missing = [v for v in required_vars if not os.environ.get(v)]
    if missing:
        print(f"Error: Missing environment variables: {', '.join(missing)}")
        sys.exit(1)

    # --- Production series ---
    print("Fetching production data from FRED...")
    results = []
    for series_id, info in SERIES.items():
        print(f"  {info['name']} ({series_id})...")
        data = fetch_series(series_id)
        metrics = compute_metrics(data)
        chart_png = make_chart(data, info, metrics)
        yoy_chart_png = make_yoy_chart(data, info)
        results.append({
            "info": info,
            "metrics": metrics,
            "chart_png": chart_png,
            "yoy_chart_png": yoy_chart_png,
        })
        print(f"    Latest: {metrics['latest_value']:.1f} ({metrics['latest_date'].strftime('%b %Y')})")
        print(f"    MoM: {metrics['mom_change']:+.2f}%  |  YoY: {metrics['yoy_change']:+.2f}%")
        print(f"    10Y Peak: {metrics['peak_10y_value']:.1f} ({metrics['peak_10y_date'].strftime('%b %Y')})  |  vs 10Y Peak: {metrics['off_peak_10y']:+.2f}%")
        print(f"    AT Peak: {metrics['peak_value']:.1f} ({metrics['peak_date'].strftime('%b %Y')})  |  vs AT Peak: {metrics['off_peak']:+.2f}%")

    # --- Capacity utilization series ---
    print("\nFetching capacity utilization data from FRED...")
    cap_util_data = []
    for series_id, info in CAPACITY_UTIL_SERIES.items():
        print(f"  {info['name']} ({series_id})...")
        data = fetch_series(series_id)
        metrics = compute_metrics(data)
        cap_util_data.append({"info": info, "metrics": metrics})
        print(f"    Utilization: {metrics['latest_value']:.1f}% ({metrics['latest_date'].strftime('%b %Y')})")
        print(f"    MoM: {metrics['mom_change']:+.2f}%  |  YoY: {metrics['yoy_change']:+.2f}%")

    # --- Steel imports ---
    print("\nFetching steel import data from Census Bureau...")
    import_tables = []
    import_charts = []
    for imp in IMPORT_SERIES:
        print(f"  {imp['name']}...")
        accum = fetch_import_raw(imp)
        tbl = build_import_table_data(imp, accum)
        import_tables.append(tbl)
        chart_png = make_import_stacked_chart(imp, accum)
        import_charts.append((imp["name"], chart_png))

    print("\nBuilding HTML report...")
    html, images = build_html(results, cap_util_data, import_tables,
                              import_charts=import_charts, preview=args.preview)

    if args.out_file:
        with open(args.out_file, "w") as f:
            f.write(html)
        print(f"HTML saved to {args.out_file}")

    if args.preview:
        preview_path = os.path.join(os.path.dirname(__file__), "preview.html")
        with open(preview_path, "w") as f:
            f.write(html)
        print(f"Preview saved to {preview_path}")
        webbrowser.open(f"file://{os.path.abspath(preview_path)}")
        print("Opened in browser.")
    else:
        print(f"Sending email to {REPORT_RECIPIENT}...")
        send_email(html, images)
        print("Done! Report sent successfully.")


if __name__ == "__main__":
    main()
