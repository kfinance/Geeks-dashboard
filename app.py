"""
app.py
Options Greeks Dashboard — Streamlit app.

Three views:
  1. Chain View       - Greeks across the full strike chain for a chosen expiry
  2. Single Option     - Detailed Greeks + payoff for one strike, with IV solved from LTP
  3. Portfolio Builder  - Multi-leg positions (straddle/strangle/spread etc.)
                          with aggregated net Greeks — the "trading desk risk view"

Run with:  streamlit run app.py
"""

import datetime as dt
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from greeks import all_greeks, bs_price, implied_volatility
from data_fetch import get_chain

st.set_page_config(page_title="Options Greeks Dashboard", layout="wide")

RISK_FREE_RATE = 0.065  # ~ current India 91-day T-bill proxy; adjust as needed


def _iv_or_default(value, default=15.0):
    """Fall back to a default IV when the chain has no quote (None/NaN)
    — using `pd.isna` rather than truthiness so a legitimately-quoted
    IV of 0 isn't mistaken for "missing"."""
    return default if pd.isna(value) else value

# ---------------------------------------------------------------------------
# Sidebar — global controls
# ---------------------------------------------------------------------------
st.sidebar.title("Controls")
symbol = st.sidebar.selectbox("Underlying", ["NIFTY", "BANKNIFTY"])
use_live = st.sidebar.checkbox("Try live NSE data", value=True,
                                help="Falls back to a sample chain if NSE blocks the request "
                                     "(common on hosted/cloud environments).")
r = st.sidebar.number_input("Risk-free rate (annual, %)", value=RISK_FREE_RATE * 100, step=0.25) / 100

df, spot, is_live = get_chain(symbol, use_live=use_live)
expiries = sorted(df["expiry"].unique())
expiry_str = st.sidebar.selectbox("Expiry", expiries)

data_badge = "🟢 Live NSE data" if is_live else "🟡 Sample data (NSE unreachable from this environment)"
st.sidebar.caption(data_badge)

# time to expiry in years
def _parse_expiry(expiry_str):
    """Parse an expiry string from either the sample chain or live NSE
    data — NSE has been known to vary format/precision, so try a few."""
    for fmt in ("%d-%b-%Y", "%d-%b-%Y %H:%M:%S", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(expiry_str, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Unrecognized expiry date format: {expiry_str!r}")

try:
    expiry_date = _parse_expiry(expiry_str)
except ValueError as e:
    st.error(f"Could not parse expiry date: {e}")
    st.stop()
T_days = max((expiry_date - dt.date.today()).days, 0)
T = T_days / 365.0

chain = df[df["expiry"] == expiry_str].copy().reset_index(drop=True)

st.title(f"{symbol} Options Greeks Dashboard")
st.caption(f"Spot: {spot:,.2f}  |  Expiry: {expiry_str}  ({T_days} days)  |  r = {r*100:.2f}%")

tab1, tab2, tab3 = st.tabs(["📊 Chain View", "🔍 Single Option", "🧮 Portfolio Builder"])

# ---------------------------------------------------------------------------
# TAB 1 — Chain view: Greeks across all strikes
# ---------------------------------------------------------------------------
with tab1:
    st.subheader("Greeks across the strike chain")

    rows = []
    for _, row in chain.iterrows():
        K = row["strike"]
        ce_iv = _iv_or_default(row["CE_IV"]) / 100
        pe_iv = _iv_or_default(row["PE_IV"]) / 100
        ce = all_greeks(spot, K, T, r, ce_iv, "call")
        pe = all_greeks(spot, K, T, r, pe_iv, "put")
        rows.append({
            "Strike": K,
            "CE Price": round(ce["price"], 2), "CE Delta": round(ce["delta"], 3),
            "CE Gamma": round(ce["gamma"], 4), "CE Theta": round(ce["theta"], 2),
            "CE Vega": round(ce["vega"], 2),
            "PE Price": round(pe["price"], 2), "PE Delta": round(pe["delta"], 3),
            "PE Gamma": round(pe["gamma"], 4), "PE Theta": round(pe["theta"], 2),
            "PE Vega": round(pe["vega"], 2),
        })
    greeks_df = pd.DataFrame(rows)

    st.dataframe(greeks_df, use_container_width=True, hide_index=True)

    metric = st.selectbox("Plot Greek across strikes", ["Delta", "Gamma", "Theta", "Vega"])
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=greeks_df["Strike"], y=greeks_df[f"CE {metric}"],
                              name=f"Call {metric}", mode="lines+markers"))
    fig.add_trace(go.Scatter(x=greeks_df["Strike"], y=greeks_df[f"PE {metric}"],
                              name=f"Put {metric}", mode="lines+markers"))
    fig.add_vline(x=spot, line_dash="dash", line_color="gray", annotation_text="Spot")
    fig.update_layout(title=f"{metric} across strikes ({symbol}, {expiry_str})",
                       xaxis_title="Strike", yaxis_title=metric, height=450)
    st.plotly_chart(fig, use_container_width=True)

# ---------------------------------------------------------------------------
# TAB 2 — Single option deep-dive
# ---------------------------------------------------------------------------
with tab2:
    st.subheader("Single option detail")
    col1, col2, col3 = st.columns(3)
    with col1:
        K_sel = st.selectbox("Strike", sorted(chain["strike"].unique()),
                              index=len(chain)//2)
    with col2:
        opt_type = st.radio("Type", ["call", "put"], horizontal=True)
    with col3:
        iv_input_mode = st.radio("IV source", ["From chain", "Manual"], horizontal=True)

    row = chain[chain["strike"] == K_sel].iloc[0]
    chain_iv = _iv_or_default(row["CE_IV"] if opt_type == "call" else row["PE_IV"])
    market_ltp = row["CE_LTP"] if opt_type == "call" else row["PE_LTP"]

    if iv_input_mode == "Manual":
        iv_pct = st.slider("Implied volatility (%)", 5.0, 100.0, float(chain_iv), 0.5)
    else:
        iv_pct = float(chain_iv)
    sigma = iv_pct / 100

    g = all_greeks(spot, K_sel, T, r, sigma, opt_type)

    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("Theoretical Price", f"{g['price']:.2f}")
    m2.metric("Delta", f"{g['delta']:.3f}")
    m3.metric("Gamma", f"{g['gamma']:.4f}")
    m4.metric("Theta/day", f"{g['theta']:.2f}")
    m5.metric("Vega", f"{g['vega']:.2f}")
    m6.metric("Rho", f"{g['rho']:.3f}")

    if market_ltp:
        implied_from_market = implied_volatility(market_ltp, spot, K_sel, T, r, opt_type)
        st.caption(f"Chain LTP: {market_ltp:.2f}  |  IV backed out from LTP: "
                   f"{implied_from_market*100:.2f}%  |  Chain-quoted IV: {chain_iv:.2f}%")

    # Payoff diagram at expiry vs current theoretical value
    spot_range = np.linspace(spot * 0.85, spot * 1.15, 100)
    if opt_type == "call":
        payoff = np.maximum(spot_range - K_sel, 0) - g["price"]
    else:
        payoff = np.maximum(K_sel - spot_range, 0) - g["price"]

    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(x=spot_range, y=payoff, name="P&L at expiry", mode="lines"))
    fig2.add_hline(y=0, line_dash="dot", line_color="gray")
    fig2.add_vline(x=spot, line_dash="dash", line_color="blue", annotation_text="Spot")
    fig2.add_vline(x=K_sel, line_dash="dash", line_color="orange", annotation_text="Strike")
    fig2.update_layout(title=f"P&L at expiry — {opt_type.upper()} {K_sel}",
                        xaxis_title="Underlying at expiry", yaxis_title="P&L per share", height=400)
    st.plotly_chart(fig2, use_container_width=True)

# ---------------------------------------------------------------------------
# TAB 3 — Portfolio builder: multi-leg net Greeks (the desk risk view)
# ---------------------------------------------------------------------------
with tab3:
    st.subheader("Multi-leg portfolio — net Greeks")
    st.caption("Build a strategy (straddle, strangle, spread, etc.) and see the aggregated "
               "position Greeks — this mirrors a live trading-desk risk screen.")

    if "legs" not in st.session_state:
        st.session_state.legs = []

    with st.form("add_leg", clear_on_submit=True):
        c1, c2, c3, c4, c5 = st.columns(5)
        with c1:
            leg_K = st.selectbox("Strike", sorted(chain["strike"].unique()), key="leg_K")
        with c2:
            leg_type = st.selectbox("Type", ["call", "put"], key="leg_type")
        with c3:
            leg_side = st.selectbox("Side", ["Buy", "Sell"], key="leg_side")
        with c4:
            leg_qty = st.number_input("Lots", min_value=1, value=1, key="leg_qty")
        with c5:
            leg_iv = st.number_input("IV (%)", value=15.0, key="leg_iv")
        submitted = st.form_submit_button("Add leg")
        if submitted:
            st.session_state.legs.append({
                "strike": leg_K, "type": leg_type, "side": leg_side,
                "qty": leg_qty, "iv": leg_iv
            })

    if st.session_state.legs:
        leg_rows = []
        net = {"delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0, "rho": 0.0}
        for i, leg in enumerate(st.session_state.legs):
            sign = 1 if leg["side"] == "Buy" else -1
            g = all_greeks(spot, leg["strike"], T, r, leg["iv"] / 100, leg["type"])
            for k in net:
                net[k] += sign * leg["qty"] * g[k]
            leg_rows.append({
                "#": i, "Side": leg["side"], "Type": leg["type"].upper(),
                "Strike": leg["strike"], "Lots": leg["qty"], "IV%": leg["iv"],
                "Price": round(g["price"], 2), "Delta": round(sign * g["delta"], 3),
                "Gamma": round(sign * g["gamma"], 4), "Theta": round(sign * g["theta"], 2),
                "Vega": round(sign * g["vega"], 2),
            })

        st.dataframe(pd.DataFrame(leg_rows), use_container_width=True, hide_index=True)

        col1, col2 = st.columns([3, 1])
        with col2:
            if st.button("Clear all legs"):
                st.session_state.legs = []
                st.rerun()

        n1, n2, n3, n4, n5 = st.columns(5)
        n1.metric("Net Delta", f"{net['delta']:.3f}")
        n2.metric("Net Gamma", f"{net['gamma']:.4f}")
        n3.metric("Net Theta/day", f"{net['theta']:.2f}")
        n4.metric("Net Vega", f"{net['vega']:.2f}")
        n5.metric("Net Rho", f"{net['rho']:.3f}")

        # Combined payoff diagram
        spot_range = np.linspace(spot * 0.85, spot * 1.15, 200)
        total_payoff = np.zeros_like(spot_range)
        for leg in st.session_state.legs:
            sign = 1 if leg["side"] == "Buy" else -1
            g = all_greeks(spot, leg["strike"], T, r, leg["iv"] / 100, leg["type"])
            if leg["type"] == "call":
                intrinsic = np.maximum(spot_range - leg["strike"], 0)
            else:
                intrinsic = np.maximum(leg["strike"] - spot_range, 0)
            total_payoff += sign * leg["qty"] * (intrinsic - g["price"])

        fig3 = go.Figure()
        fig3.add_trace(go.Scatter(x=spot_range, y=total_payoff, name="Net P&L at expiry", mode="lines"))
        fig3.add_hline(y=0, line_dash="dot", line_color="gray")
        fig3.add_vline(x=spot, line_dash="dash", line_color="blue", annotation_text="Spot")
        fig3.update_layout(title="Combined position P&L at expiry",
                            xaxis_title="Underlying at expiry", yaxis_title="Net P&L", height=400)
        st.plotly_chart(fig3, use_container_width=True)
    else:
        st.info("Add legs above to build a strategy (e.g. straddle = Buy Call + Buy Put, same strike).")

st.divider()
st.caption("Built with Black-Scholes-Merton pricing. Live IVs shown for context; "
           "manual IV override available for what-if scenario testing. Educational use only.")
