"""
Stock dashboard with DCF-based intrinsic value for every stock.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import stock_data

st.set_page_config(
    page_title="Stock Dashboard | DCF Intrinsic Value",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Default tickers
DEFAULT_TICKERS = "AAPL, MSFT, GOOGL, AMZN, META, NVDA, BRK-B, JPM, V, JNJ, WMT, PG, UNH, HD, DIS"

st.title("📈 Stock Dashboard — DCF Intrinsic Value")
st.markdown(
    "Look up **any stock** by ticker for price, financial ratios, and a **buy score (1–100)**. "
    "Below, intrinsic value for every stock in your watchlist is computed with a **DCF** model."
)

# ----- Stock Lookup: type ticker to see price, ratios, buy score -----
lookup_symbol = st.text_input(
    "🔍 **Look up a stock** — enter ticker symbol",
    value="",
    placeholder="e.g. AAPL, TSLA, NVDA",
    key="lookup_ticker",
    label_visibility="collapsed",
).strip().upper()
if lookup_symbol:
    st.caption(f"Showing results for **{lookup_symbol}**")

# Sidebar: DCF assumptions
st.sidebar.header("DCF assumptions")
growth_rate = st.sidebar.slider(
    "FCF growth rate (% per year)",
    0.0, 25.0, 8.0, 0.5,
    help="Expected annual growth in Free Cash Flow during projection period.",
) / 100.0
terminal_growth = st.sidebar.slider(
    "Terminal growth rate (%)",
    0.0, 6.0, 2.5, 0.1,
    help="Perpetual growth rate after projection period (e.g. long-term GDP).",
) / 100.0
discount_rate = st.sidebar.slider(
    "Discount rate / WACC (%)",
    5.0, 20.0, 10.0, 0.5,
    help="Required return used to discount future cash flows.",
) / 100.0
projection_years = st.sidebar.slider(
    "Projection years",
    5, 15, 10, 1,
    help="Number of years of explicit FCF projection before terminal value.",
)

st.sidebar.markdown("---")
st.sidebar.markdown(
    "**DCF formula:**  \n"
    "Value = Σ FCFₜ/(1+r)ᵗ + TV/(1+r)ᵀ  \n"
    "TV = FCFₜ×(1+g_term)/(r−g_term)"
)

# ----- Ticker input (watchlist for DCF table) -----
st.sidebar.markdown("---")
st.sidebar.subheader("Watchlist (DCF table)")
tickers_raw = st.sidebar.text_area(
    "Tickers (comma-separated)",
    value=DEFAULT_TICKERS,
    height=120,
)
tickers = [t.strip().upper() for t in tickers_raw.replace("\n", ",").split(",") if t.strip()]
if not tickers:
    st.warning("Enter at least one ticker in the watchlist.")
    st.stop()

# ----- Stock Lookup results (when a symbol is entered) -----
if lookup_symbol:
    with st.spinner(f"Looking up {lookup_symbol}..."):
        lookup = stock_data.get_stock_lookup(
            lookup_symbol,
            growth_rate=growth_rate,
            terminal_growth=terminal_growth,
            discount_rate=discount_rate,
            projection_years=projection_years,
        )
    with st.container():
        st.subheader(f"🔍 {lookup.get('name', lookup_symbol)} ({lookup_symbol})")
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            price = lookup.get("current_price")
            st.metric("Stock price", f"${price:,.2f}" if price is not None else "—")
        with c2:
            iv = lookup.get("intrinsic_value")
            st.metric("DCF intrinsic value", f"${iv:,.2f}" if iv is not None else "—")
        with c3:
            mos = lookup.get("margin_of_safety_pct")
            st.metric("Margin of safety %", f"{mos:.1f}%" if mos is not None else "—")
        with c4:
            score = lookup.get("buy_score")
            st.metric("Buy score (1–100)", f"{int(score)}" if score is not None else "—")
        if lookup.get("buy_label"):
            st.info(f"**{lookup['buy_label']}**")
        if lookup.get("error"):
            st.warning(f"Note: {lookup['error']}")

        st.markdown("**Financial ratios**")
        ratios = lookup.get("ratios") or {}
        # Format ratio values for display
        def fmt(v):
            if v is None:
                return "—"
            if isinstance(v, float):
                if v >= 1e12:
                    return f"${v/1e12:.2f}T"
                if v >= 1e9:
                    return f"${v/1e9:.2f}B"
                if v >= 1e6:
                    return f"${v/1e6:.2f}M"
                if abs(v) < 0.01 and v != 0:
                    return f"{v:.4f}"
                return f"{v:.2f}"
            return str(v)
        r1, r2, r3 = st.columns(3)
        with r1:
            for k in ["P/E (trailing)", "P/E (forward)", "P/B", "P/S"]:
                st.caption(f"{k}: {fmt(ratios.get(k))}")
        with r2:
            for k in ["ROE %", "ROA %", "Profit margin %", "Revenue growth %"]:
                v = ratios.get(k)
                st.caption(f"{k}: {f'{v:.1f}%' if v is not None and v == v else '—'}")
        with r3:
            for k in ["Debt/Equity", "Current ratio", "Quick ratio", "Market cap"]:
                st.caption(f"{k}: {fmt(ratios.get(k))}")
    st.markdown("---")

if st.sidebar.button("Refresh data"):
    st.rerun()

# Fetch valuations
with st.spinner("Computing DCF intrinsic values..."):
    df = stock_data.build_valuation_table(
        tickers,
        growth_rate=growth_rate,
        terminal_growth=terminal_growth,
        discount_rate=discount_rate,
        projection_years=projection_years,
    )

# Summary metrics
ok = df["Error"].isna()
n_ok = ok.sum()
n_err = (~ok).sum()
col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Stocks analyzed", len(df))
with col2:
    st.metric("With DCF value", n_ok)
with col3:
    if n_ok > 0:
        avg_mos = df.loc[ok, "Margin of Safety %"].mean()
        st.metric("Avg margin of safety %", f"{avg_mos:.1f}%")
    else:
        st.metric("Avg margin of safety %", "—")

# Main table: format numbers
display_df = df.copy()
display_df["Price"] = display_df["Price"].apply(lambda x: f"${x:,.2f}" if pd.notna(x) and x else "—")
display_df["DCF Intrinsic Value"] = display_df["DCF Intrinsic Value"].apply(
    lambda x: f"${x:,.2f}" if pd.notna(x) and x else "—"
)
display_df["Margin of Safety %"] = display_df["Margin of Safety %"].apply(
    lambda x: f"{x:.1f}%" if pd.notna(x) else "—"
)
display_df["Undervalued %"] = display_df["Undervalued %"].apply(
    lambda x: f"{x:.1f}%" if pd.notna(x) else "—"
)
display_df["Error"] = display_df["Error"].fillna("—")

st.subheader("Price vs DCF intrinsic value")
st.dataframe(
    display_df,
    use_container_width=True,
    hide_index=True,
)

# Price vs intrinsic value bar chart (only rows with both)
plot_df = df[ok & df["Price"].notna() & df["DCF Intrinsic Value"].notna()].copy()
if not plot_df.empty:
    plot_df["Undervalued"] = plot_df["DCF Intrinsic Value"] > plot_df["Price"]
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=plot_df["Symbol"],
            y=plot_df["Price"],
            name="Current price",
            marker_color="steelblue",
        )
    )
    fig.add_trace(
        go.Bar(
            x=plot_df["Symbol"],
            y=plot_df["DCF Intrinsic Value"],
            name="DCF intrinsic value",
            marker_color="darkgreen",
        )
    )
    fig.update_layout(
        barmode="group",
        title="Price vs DCF intrinsic value by stock",
        xaxis_title="Symbol",
        yaxis_title="USD",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        height=400,
    )
    st.plotly_chart(fig, use_container_width=True)

# Margin of safety distribution
if not plot_df.empty and plot_df["Margin of Safety %"].notna().any():
    fig2 = px.bar(
        plot_df.sort_values("Margin of Safety %", ascending=True),
        x="Symbol",
        y="Margin of Safety %",
        title="Margin of safety (%) — positive = potential undervaluation",
        color="Margin of Safety %",
        color_continuous_scale=["red", "yellow", "green"],
        color_continuous_midpoint=0,
    )
    fig2.add_hline(y=0, line_dash="dash", line_color="gray")
    fig2.update_layout(height=350, showlegend=False)
    st.plotly_chart(fig2, use_container_width=True)

# DCF methodology expander
with st.expander("DCF methodology"):
    st.markdown(
        """
        - **Free Cash Flow (FCF)** = Operating Cash Flow − Capital Expenditures (from annual cash flow statement).
        - **Base FCF** = most recent annual FCF.
        - **Explicit period**: FCF is projected for **projection years** at **FCF growth rate**, then discounted at **discount rate**.
        - **Terminal value**: After the explicit period, FCF is assumed to grow at **terminal growth rate** forever; 
          TV = FCF_T × (1 + g_term) / (r − g_term), then discounted to present.
        - **Intrinsic value per share** = (PV of explicit FCFs + PV of terminal value) / shares outstanding.
        - **Margin of safety %** = (1 − Price / Intrinsic value) × 100. **Positive** = trades below DCF (potential undervaluation); **negative** = trades above DCF (potential overvaluation).
        """
    )
    st.markdown("Assumptions used in this run:")
    st.json({
        "FCF growth rate": f"{growth_rate*100:.1f}%",
        "Terminal growth rate": f"{terminal_growth*100:.1f}%",
        "Discount rate (WACC)": f"{discount_rate*100:.1f}%",
        "Projection years": projection_years,
    })

st.caption("Data: Yahoo Finance. DCF model is illustrative; adjust assumptions in the sidebar.")
