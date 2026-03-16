"""
DCF (Discounted Cash Flow) intrinsic value calculator for equities.
Uses free cash flow, growth assumptions, and WACC to estimate fair value per share.
"""

import numpy as np
import pandas as pd
from typing import Optional


def _normalize_key(d: dict, *candidates: str) -> Optional[float]:
    """Get first matching key from dict (case-insensitive, partial match)."""
    keys_lower = {k.lower(): k for k in d.index if isinstance(k, str)}
    for c in candidates:
        c = c.lower()
        for k, orig in keys_lower.items():
            if c in k:
                return d.get(orig)
    return None


def get_fcf_series(cashflow_df: pd.DataFrame) -> Optional[pd.Series]:
    """
    Derive Free Cash Flow from cash flow statement.
    FCF = Operating Cash Flow - Capital Expenditures
    """
    if cashflow_df is None or cashflow_df.empty:
        return None
    # Handle DataFrame: rows are line items, columns are dates
    out = []
    for col in cashflow_df.columns:
        row = cashflow_df[col]
        ocf = _normalize_key(
            row,
            "total cash from operating activities",
            "operating cash flow",
            "cash from operating activities",
        )
        capex = _normalize_key(
            row,
            "capital expenditure",
            "capital expenditures",
            "purchase of property",
        )
        if ocf is not None and capex is not None:
            out.append((col, ocf - capex))
        elif ocf is not None:
            out.append((col, ocf))
    if not out:
        return None
    return pd.Series({d: v for d, v in out}).sort_index(ascending=False)


def dcf_intrinsic_value(
    fcf_series: pd.Series,
    shares_outstanding: float,
    *,
    growth_rate: float = 0.08,
    terminal_growth: float = 0.025,
    discount_rate: float = 0.10,
    projection_years: int = 10,
    fcf_base: Optional[float] = None,
) -> dict:
    """
    Compute DCF intrinsic value per share.

    Parameters
    ----------
    fcf_series : pd.Series
        Historical FCF (index = dates, values = FCF). Newest first.
    shares_outstanding : float
        Number of shares outstanding.
    growth_rate : float
        Annual FCF growth rate for projection period (e.g. 0.08 = 8%).
    terminal_growth : float
        Perpetual growth rate after projection (e.g. 0.025 = 2.5%).
    discount_rate : float
        WACC / required return (e.g. 0.10 = 10%).
    projection_years : int
        Years of explicit FCF projection.
    fcf_base : float, optional
        Base FCF for year 0. If None, uses latest from fcf_series.

    Returns
    -------
    dict with keys: intrinsic_value_per_share, total_ev, fcf_base_used,
                    pv_explicit, pv_terminal, assumptions.
    """
    if fcf_series is None or fcf_series.empty or shares_outstanding <= 0:
        return {
            "intrinsic_value_per_share": None,
            "total_ev": None,
            "fcf_base_used": None,
            "pv_explicit": None,
            "pv_terminal": None,
            "error": "Missing FCF or shares",
            "assumptions": {},
        }

    fcf_base = float(fcf_base) if fcf_base is not None else float(fcf_series.iloc[0])
    if np.isnan(fcf_base) or fcf_base <= 0:
        return {
            "intrinsic_value_per_share": None,
            "total_ev": None,
            "fcf_base_used": None,
            "pv_explicit": None,
            "pv_terminal": None,
            "error": "Invalid base FCF",
            "assumptions": {},
        }

    r = discount_rate
    g = growth_rate
    g_term = terminal_growth

    # Explicit period: FCF_t = FCF_0 * (1+g)^t, PV = FCF_t / (1+r)^t
    pv_explicit = 0.0
    for t in range(1, projection_years + 1):
        fcf_t = fcf_base * ((1 + g) ** t)
        pv_explicit += fcf_t / ((1 + r) ** t)

    # Terminal value at end of projection: TV = FCF_T * (1 + g_term) / (r - g_term)
    fcf_T = fcf_base * ((1 + g) ** projection_years)
    if r <= g_term:
        pv_terminal = 0.0
    else:
        terminal_value = fcf_T * (1 + g_term) / (r - g_term)
        pv_terminal = terminal_value / ((1 + r) ** projection_years)

    total_ev = pv_explicit + pv_terminal
    intrinsic_per_share = total_ev / shares_outstanding

    assumptions = {
        "growth_rate": growth_rate,
        "terminal_growth": terminal_growth,
        "discount_rate": discount_rate,
        "projection_years": projection_years,
    }
    return {
        "intrinsic_value_per_share": intrinsic_per_share,
        "total_ev": total_ev,
        "fcf_base_used": fcf_base,
        "pv_explicit": pv_explicit,
        "pv_terminal": pv_terminal,
        "error": None,
        "assumptions": assumptions,
    }
