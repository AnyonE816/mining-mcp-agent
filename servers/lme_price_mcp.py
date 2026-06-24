"""MCP Server 2: lme-price — 金属/矿产价格查询

Tools:
  - get_price(commodity, date)  → 某商品某日价格
  - get_trend(commodity, days)  → 某商品近期价格趋势

数据源:
  - 铜/锌/镍: akshare SHFE 期货 (futures_main_sina)
  - 锂: spodumene concentrate 6% Li2O CIF China — demo 数据 (基于 Argus/Fastmarkets 公开报价)
  - fallback: demo 数据确保任何情况下可跑

Transport: stdio
"""

from datetime import datetime, timedelta
from typing import Any

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("lme-price")

# ---------------------------------------------------------------------------
# Commodity → akshare symbol mapping
# SHFE futures via akshare.futures_main_sina()
# ---------------------------------------------------------------------------
AKSHARE_SYMBOLS = {
    "copper": "CU0",
    "zinc": "ZN0",
    "nickel": "NI0",
    "aluminum": "AL0",
    "iron_ore": "I0",
}

# ---------------------------------------------------------------------------
# Demo price data (per tonne, USD or CNY as noted)
# Lithium: spodumene concentrate 6% Li2O CIF China, USD/t
# LME metals: approximate recent levels, USD/t
# ---------------------------------------------------------------------------
DEMO_PRICES = {
    "lithium": {
        "price": 607.50,
        "unit": "USD/tonne",
        "description": "Spodumene concentrate 6% Li2O CIF China (Argus assessment, late June 2025)",
    },
    "copper": {
        "price": 9850,
        "unit": "USD/tonne",
        "description": "LME Copper 3M (approximate, June 2025)",
    },
    "zinc": {
        "price": 2980,
        "unit": "USD/tonne",
        "description": "LME Zinc 3M (approximate, June 2025)",
    },
    "nickel": {
        "price": 16800,
        "unit": "USD/tonne",
        "description": "LME Nickel 3M (approximate, June 2025)",
    },
    "aluminum": {
        "price": 2550,
        "unit": "USD/tonne",
        "description": "LME Aluminum 3M (approximate, June 2025)",
    },
    "iron_ore": {
        "price": 108,
        "unit": "USD/tonne",
        "description": "62% Fe fines CFR China (approximate, June 2025)",
    },
}

# Lithium trend (quarterly, 2025–2026)
LITHIUM_TREND = [
    {"date": "2025-12-31", "price": 770},
    {"date": "2026-01-31", "price": 750},
    {"date": "2026-02-28", "price": 720},
    {"date": "2026-03-31", "price": 680},
    {"date": "2026-04-30", "price": 640},
    {"date": "2026-05-31", "price": 620},
    {"date": "2026-06-24", "price": 607.50},
]


def _fetch_akshare(commodity: str, days: int) -> list[dict[str, Any]]:
    """Try to fetch price data from akshare. Returns [] on failure."""
    symbol = AKSHARE_SYMBOLS.get(commodity)
    if not symbol:
        return []

    try:
        import akshare as ak

        df = ak.futures_main_sina(symbol)
        if df is None or df.empty:
            return []

        cutoff = datetime.now() - timedelta(days=days)
        df = df[df["日期"] >= cutoff.strftime("%Y-%m-%d")]
        if df.empty:
            return []

        return [
            {
                "date": str(row["日期"]),
                "open": float(row["开盘价"]),
                "high": float(row["最高价"]),
                "low": float(row["最低价"]),
                "close": float(row["收盘价"]),
                "volume": int(row["成交量"]),
            }
            for _, row in df.tail(days).iterrows()
        ]
    except Exception:
        return []


def _demo_trend(commodity: str, days: int) -> list[dict[str, Any]]:
    """Generate demo trend data for commodities not covered by akshare."""
    if commodity == "lithium":
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        return [d for d in LITHIUM_TREND if d["date"] >= cutoff]

    info = DEMO_PRICES.get(commodity, {})
    if not info:
        return [{"error": f"Unknown commodity: {commodity}"}]

    today = datetime.now().strftime("%Y-%m-%d")
    return [{"date": today, "price": info["price"], "unit": info["unit"]}]


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def get_price(commodity: str, date: str | None = None) -> dict[str, Any]:
    """Get the latest or historical price for a commodity.

    Args:
        commodity: Commodity name — 'copper', 'zinc', 'nickel', 'aluminum',
                   'iron_ore', or 'lithium'
        date: Date in YYYY-MM-DD format. If omitted, returns latest available.
    """
    commodity = commodity.lower().strip()

    # Try akshare first for SHFE-traded commodities
    akshare_data = _fetch_akshare(commodity, days=7)
    if akshare_data:
        target = date if date else akshare_data[-1]["date"]
        for row in akshare_data:
            if row["date"] == target:
                return {
                    "commodity": commodity,
                    "date": row["date"],
                    "price": row["close"],
                    "unit": "CNY/tonne (SHFE)",
                    "source": "akshare (Sina Finance)",
                }
        # Date not found, return latest
        latest = akshare_data[-1]
        return {
            "commodity": commodity,
            "date": latest["date"],
            "price": latest["close"],
            "unit": "CNY/tonne (SHFE)",
            "source": "akshare (Sina Finance)",
        }

    # Fallback to demo data
    info = DEMO_PRICES.get(commodity)
    if not info:
        return {"error": f"Unknown commodity: '{commodity}'. Supported: {list(DEMO_PRICES)}"}

    return {
        "commodity": commodity,
        "date": date or datetime.now().strftime("%Y-%m-%d"),
        "price": info["price"],
        "unit": info["unit"],
        "description": info["description"],
        "source": "demo (benchmark estimates)",
        "note": "Demo data — replace with live API in production",
    }


@mcp.tool()
async def get_trend(commodity: str, days: int = 30) -> list[dict[str, Any]]:
    """Get price trend for a commodity over a number of days.

    Args:
        commodity: Commodity name — 'copper', 'zinc', 'nickel', 'aluminum',
                   'iron_ore', or 'lithium'
        days: Number of days of history (default 30)
    """
    commodity = commodity.lower().strip()

    # Try akshare first
    akshare_data = _fetch_akshare(commodity, days)
    if akshare_data:
        return [
            {
                "date": r["date"],
                "close": r["close"],
                "unit": "CNY/tonne (SHFE)",
                "source": "akshare",
            }
            for r in akshare_data
        ]

    # Demo fallback
    trend = _demo_trend(commodity, days)
    if trend and "error" in trend[0]:
        return trend

    info = DEMO_PRICES.get(commodity, {})
    return [
        {**d, "unit": info.get("unit", "USD/tonne"), "source": "demo (benchmark estimates)"}
        for d in trend
    ]


if __name__ == "__main__":
    mcp.run(transport="stdio")
