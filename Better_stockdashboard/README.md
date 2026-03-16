# Stock Dashboard — DCF Intrinsic Value

A stock dashboard that computes **intrinsic value for every stock** using a **Discounted Cash Flow (DCF)** model.

## Features

- **Per-stock DCF**: Each ticker gets its own DCF-based intrinsic value from reported Free Cash Flow (FCF).
- **Configurable assumptions**: FCF growth rate, terminal growth, discount rate (WACC), and projection years in the sidebar.
- **Valuation metrics**: Current price, DCF fair value, **margin of safety %**, and **undervalued %**.
- **Charts**: Price vs intrinsic value by stock; margin of safety distribution.

## Run

```bash
cd stock_dashboard
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/streamlit run app.py
```

Open the URL shown in the terminal (e.g. http://localhost:8501).

## DCF Model

- **FCF** = Operating Cash Flow − Capital Expenditures (from annual cash flow statement).
- **Explicit period**: FCF is projected for N years at the chosen growth rate and discounted at the chosen discount rate.
- **Terminal value**: After N years, FCF grows at the terminal growth rate in perpetuity; TV is discounted to present.
- **Intrinsic value per share** = (PV of explicit FCFs + PV of terminal value) / shares outstanding.

Data source: Yahoo Finance via `yfinance`.
