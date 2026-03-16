"""
Fetch stock data and compute DCF intrinsic value using yfinance.
"""

import pandas as pd
import yfinance as yf
from typing import Optional
import dcf


def _get_cashflow(ticker: yf.Ticker) -> Optional[pd.DataFrame]:
    """Get annual cash flow statement."""
    try:
        cf = ticker.get_cashflow()
        if cf is not None and not cf.empty:
            return cf
        cf = getattr(ticker, "cashflow", None)
        return cf if cf is not None and not cf.empty else None
    except Exception:
        return None


def _get_shares_outstanding(ticker: yf.Ticker) -> Optional[float]:
    """Shares outstanding from info or balance sheet."""
    try:
        info = ticker.info
        for key in ("sharesOutstanding", "floatShares", "impliedSharesOutstanding"):
            v = info.get(key)
            if v is not None and (isinstance(v, (int, float)) and v > 0):
                return float(v)
        # Fallback: balance sheet "Share Issued" or similar
        bs = ticker.balance_sheet
        if bs is not None and not bs.empty:
            for idx in bs.index:
                if isinstance(idx, str) and "share" in idx.lower() and "issued" in idx.lower():
                    val = bs.loc[idx].iloc[0]
                    if pd.notna(val) and val > 0:
                        return float(val)
    except Exception:
        pass
    return None


def _fcf_from_cashflow(cf: pd.DataFrame) -> Optional[pd.Series]:
    """Extract FCF from yfinance-style cash flow DataFrame."""
    if cf is None or cf.empty:
        return None
    # Rows are line items (index), columns are dates
    out = {}
    for col in cf.columns:
        row = cf[col]
        ocf = None
        capex = None
        for idx in cf.index:
            if not isinstance(idx, str):
                continue
            s = idx.lower()
            if "operating" in s and "cash" in s:
                ocf = row.get(idx)
            if "capital" in s and "expenditure" in s:
                capex = row.get(idx)
        if ocf is not None:
            fcf = ocf - capex if capex is not None else ocf
            if pd.notna(fcf):
                out[col] = float(fcf)
    if not out:
        return None
    return pd.Series(out).sort_index(ascending=False)


def get_stock_valuation(
    symbol: str,
    *,
    growth_rate: float = 0.08,
    terminal_growth: float = 0.025,
    discount_rate: float = 0.10,
    projection_years: int = 10,
) -> dict:
    """
    For a given ticker, fetch data and return current price, DCF intrinsic value,
    and valuation metrics (margin of safety, etc.).
    """
    symbol = symbol.strip().upper()
    ticker = yf.Ticker(symbol)
    result = {
        "symbol": symbol,
        "current_price": None,
        "intrinsic_value": None,
        "margin_of_safety_pct": None,
        "undervalued_pct": None,
        "dcf_result": None,
        "fcf_series": None,
        "shares_outstanding": None,
        "error": None,
    }

    try:
        # Current price
        hist = ticker.history(period="5d")
        if hist is not None and not hist.empty and "Close" in hist.columns:
            result["current_price"] = float(hist["Close"].iloc[-1])
        else:
            info = ticker.info
            result["current_price"] = info.get("currentPrice") or info.get("regularMarketPrice")
            if result["current_price"] is not None:
                result["current_price"] = float(result["current_price"])

        # Cash flow and FCF
        cf = _get_cashflow(ticker)
        fcf_series = _fcf_from_cashflow(cf) if cf is not None else dcf.get_fcf_series(cf) if cf is not None else None
        result["fcf_series"] = fcf_series

        # Shares
        shares = _get_shares_outstanding(ticker)
        result["shares_outstanding"] = shares

        if fcf_series is None or fcf_series.empty:
            result["error"] = "No FCF data"
            return result
        if shares is None or shares <= 0:
            result["error"] = "No shares outstanding"
            return result

        dcf_result = dcf.dcf_intrinsic_value(
            fcf_series,
            shares,
            growth_rate=growth_rate,
            terminal_growth=terminal_growth,
            discount_rate=discount_rate,
            projection_years=projection_years,
        )
        result["dcf_result"] = dcf_result

        if dcf_result.get("error"):
            result["error"] = dcf_result["error"]
            return result

        iv = dcf_result["intrinsic_value_per_share"]
        result["intrinsic_value"] = iv

        if result["current_price"] is not None and result["current_price"] > 0 and iv is not None:
            result["margin_of_safety_pct"] = (1 - result["current_price"] / iv) * 100
            result["undervalued_pct"] = (iv / result["current_price"] - 1) * 100

    except Exception as e:
        result["error"] = str(e)

    return result


def _safe_get(info: dict, key: str, default=None):
    """Get value from info dict; return default if missing or invalid."""
    v = info.get(key)
    if v is None or (isinstance(v, float) and (v != v or abs(v) == float("inf"))):
        return default
    return v


def _compute_buy_score(
    margin_of_safety_pct: Optional[float],
    pe: Optional[float],
    roe: Optional[float],
    profit_margin: Optional[float],
    debt_to_equity: Optional[float],
    current_ratio: Optional[float],
    revenue_growth: Optional[float],
) -> tuple[float, str]:
    """
    Composite score 1-100 and short label.
    Higher = better time to buy. Uses valuation, profitability, financial health, growth.
    """
    score = 50.0  # start neutral
    reasons = []

    # Valuation (up to ±25): margin of safety from DCF, or P/E heuristic
    if margin_of_safety_pct is not None:
        # MOS 20% -> +10, 40% -> +20, -20% -> -10
        score += min(25, max(-25, margin_of_safety_pct * 0.5))
        if margin_of_safety_pct > 10:
            reasons.append("DCF suggests undervalued")
        elif margin_of_safety_pct < -20:
            reasons.append("DCF suggests overvalued")
    elif pe is not None and pe > 0:
        # P/E 10 -> +10, P/E 20 -> 0, P/E 40+ -> -10
        if pe < 15:
            score += 12
            reasons.append("Low P/E")
        elif pe > 30:
            score -= 10
            reasons.append("High P/E")

    # Profitability (up to +15): ROE and profit margin
    if roe is not None and roe > 0:
        score += min(8, roe * 40)  # 20% ROE -> +8
    if profit_margin is not None and profit_margin > 0:
        score += min(7, profit_margin * 70)  # 10% margin -> +7

    # Financial health (up to +15): low debt, solid liquidity
    if debt_to_equity is not None:
        if debt_to_equity < 0.5:
            score += 8
            reasons.append("Low debt")
        elif debt_to_equity > 2:
            score -= 5
    if current_ratio is not None and current_ratio > 1:
        score += min(7, (current_ratio - 1) * 3)  # 2 -> +3, 3 -> +6

    # Growth (up to +10): revenue growth
    if revenue_growth is not None and revenue_growth > 0:
        score += min(10, revenue_growth * 100)

    score = max(1.0, min(100.0, round(score, 0)))
    if score >= 75:
        label = "Strong buy — attractive valuation & fundamentals"
    elif score >= 60:
        label = "Buy — good time to consider"
    elif score >= 45:
        label = "Hold — neutral; buy on dips"
    elif score >= 30:
        label = "Wait — consider buying later"
    else:
        label = "Avoid / overvalued — wait for better entry"
    return score, label


def get_stock_lookup(
    symbol: str,
    *,
    growth_rate: float = 0.08,
    terminal_growth: float = 0.025,
    discount_rate: float = 0.10,
    projection_years: int = 10,
) -> dict:
    """
    Look up a single stock: price, financial ratios, DCF intrinsic value, and buy score 1-100.
    """
    symbol = symbol.strip().upper()
    ticker = yf.Ticker(symbol)
    info = ticker.info
    result = {
        "symbol": symbol,
        "name": _safe_get(info, "shortName") or _safe_get(info, "longName") or symbol,
        "current_price": None,
        "ratios": {},
        "intrinsic_value": None,
        "margin_of_safety_pct": None,
        "buy_score": None,
        "buy_label": None,
        "error": None,
    }

    try:
        # Price
        hist = ticker.history(period="5d")
        if hist is not None and not hist.empty and "Close" in hist.columns:
            result["current_price"] = float(hist["Close"].iloc[-1])
        else:
            result["current_price"] = _safe_get(info, "currentPrice") or _safe_get(info, "regularMarketPrice")
            if result["current_price"] is not None:
                result["current_price"] = float(result["current_price"])

        # Financial ratios from info
        result["ratios"] = {
            "P/E (trailing)": _safe_get(info, "trailingPE"),
            "P/E (forward)": _safe_get(info, "forwardPE"),
            "P/B": _safe_get(info, "priceToBook"),
            "P/S": _safe_get(info, "priceToSalesTrailing12Months"),
            "ROE %": _safe_get(info, "returnOnEquity") and _safe_get(info, "returnOnEquity") * 100,
            "ROA %": _safe_get(info, "returnOnAssets") and _safe_get(info, "returnOnAssets") * 100,
            "Debt/Equity": _safe_get(info, "debtToEquity"),
            "Current ratio": _safe_get(info, "currentRatio"),
            "Quick ratio": _safe_get(info, "quickRatio"),
            "Profit margin %": _safe_get(info, "profitMargins") and _safe_get(info, "profitMargins") * 100,
            "Revenue growth %": _safe_get(info, "revenueGrowth") and _safe_get(info, "revenueGrowth") * 100,
            "Market cap": _safe_get(info, "marketCap"),
        }

        # DCF valuation for this symbol (for margin of safety and score)
        valuation = get_stock_valuation(
            symbol,
            growth_rate=growth_rate,
            terminal_growth=terminal_growth,
            discount_rate=discount_rate,
            projection_years=projection_years,
        )
        result["intrinsic_value"] = valuation.get("intrinsic_value")
        result["margin_of_safety_pct"] = valuation.get("margin_of_safety_pct")
        if valuation.get("error"):
            result["error"] = valuation["error"]

        # Buy score 1-100
        score, label = _compute_buy_score(
            margin_of_safety_pct=result["margin_of_safety_pct"],
            pe=result["ratios"].get("P/E (trailing)"),
            roe=_safe_get(info, "returnOnEquity"),
            profit_margin=_safe_get(info, "profitMargins"),
            debt_to_equity=result["ratios"].get("Debt/Equity"),
            current_ratio=result["ratios"].get("Current ratio"),
            revenue_growth=_safe_get(info, "revenueGrowth"),
        )
        result["buy_score"] = score
        result["buy_label"] = label

    except Exception as e:
        result["error"] = str(e)

    return result


def build_valuation_table(
    symbols: list[str],
    growth_rate: float = 0.08,
    terminal_growth: float = 0.025,
    discount_rate: float = 0.10,
    projection_years: int = 10,
) -> pd.DataFrame:
    """Build a DataFrame with one row per symbol: price, DCF intrinsic value, margin of safety."""
    rows = []
    for sym in symbols:
        v = get_stock_valuation(
            sym,
            growth_rate=growth_rate,
            terminal_growth=terminal_growth,
            discount_rate=discount_rate,
            projection_years=projection_years,
        )
        rows.append({
            "Symbol": v["symbol"],
            "Price": v["current_price"],
            "DCF Intrinsic Value": v["intrinsic_value"],
            "Margin of Safety %": v["margin_of_safety_pct"],
            "Undervalued %": v["undervalued_pct"],
            "Error": v["error"],
        })
    return pd.DataFrame(rows)
