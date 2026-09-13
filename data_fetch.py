"""
data_fetch.py
Pulls live option chain data for NIFTY / BANKNIFTY from NSE.

NSE's own site aggressively rate-limits / blocks non-browser requests,
so this is wrapped defensively: if the live pull fails (common on
sandboxed/cloud IPs), the dashboard falls back to a manually-entered
or sample chain so the tool still works as a portfolio demo.
"""

import datetime as dt
import pandas as pd

try:
    from nsepython import nse_optionchain_scrapper
    NSEPY_AVAILABLE = True
except Exception:
    NSEPY_AVAILABLE = False


def fetch_option_chain(symbol="NIFTY"):
    """
    Returns a tidy DataFrame with columns:
    expiry, strike, spot, CE_LTP, CE_IV, CE_OI, PE_LTP, PE_IV, PE_OI

    Raises RuntimeError if the live fetch is unavailable — caller
    should catch this and fall back to sample data.
    """
    if not NSEPY_AVAILABLE:
        raise RuntimeError("nsepython not installed")

    try:
        raw = nse_optionchain_scrapper(symbol)
    except Exception as e:
        raise RuntimeError(f"NSE fetch failed: {e}")

    spot = raw["records"]["underlyingValue"]
    rows = []
    for item in raw["records"]["data"]:
        strike = item.get("strikePrice")
        expiry = item.get("expiryDate")
        ce = item.get("CE", {})
        pe = item.get("PE", {})
        rows.append({
            "expiry": expiry,
            "strike": strike,
            "spot": spot,
            "CE_LTP": ce.get("lastPrice"),
            "CE_IV": ce.get("impliedVolatility"),
            "CE_OI": ce.get("openInterest"),
            "PE_LTP": pe.get("lastPrice"),
            "PE_IV": pe.get("impliedVolatility"),
            "PE_OI": pe.get("openInterest"),
        })
    df = pd.DataFrame(rows).dropna(subset=["strike"]).sort_values("strike")
    return df, spot


# Approximate spot level and strike spacing per symbol, used for the
# sample chain — NIFTY and BANKNIFTY trade at very different index
# levels and strike intervals, so a one-size-fits-all sample would be
# wrong (and misleading under the selected symbol's title in the UI).
_SAMPLE_DEFAULTS = {
    "NIFTY": {"spot": 24800, "step": 50},
    "BANKNIFTY": {"spot": 51500, "step": 100},
}


def sample_option_chain(symbol="NIFTY", spot=None):
    """
    Deterministic sample chain for demo/offline use — realistic strike
    spacing/spot level for the given symbol and a plausible IV smile
    shape, so the dashboard is fully demoable even when NSE blocks the
    request (e.g. from a cloud/sandbox IP, or outside market hours).
    """
    cfg = _SAMPLE_DEFAULTS.get(symbol.upper(), _SAMPLE_DEFAULTS["NIFTY"])
    step = cfg["step"]
    if spot is None:
        spot = cfg["spot"]
    strikes = list(range(int(spot // step - 10) * step, int(spot // step + 11) * step, step))
    rows = []
    nearest_expiry = _next_thursday()
    for k in strikes:
        moneyness = abs(k - spot) / spot
        # simple smile: higher IV further from ATM
        base_iv = 12.5 + moneyness * 60
        rows.append({
            "expiry": nearest_expiry.strftime("%d-%b-%Y"),
            "strike": k,
            "spot": spot,
            "CE_LTP": max(spot - k, 0) + 40,
            "CE_IV": round(base_iv, 2),
            "CE_OI": 100000,
            "PE_LTP": max(k - spot, 0) + 35,
            "PE_IV": round(base_iv + 0.6, 2),
            "PE_OI": 95000,
        })
    return pd.DataFrame(rows), spot


def _next_thursday():
    today = dt.date.today()
    days_ahead = (3 - today.weekday()) % 7  # Thursday = 3
    days_ahead = days_ahead if days_ahead != 0 else 7
    return today + dt.timedelta(days=days_ahead)


def get_chain(symbol="NIFTY", use_live=True):
    """
    Single entry point the dashboard calls. Tries live NSE data first
    (if use_live=True), falls back to sample data on any failure.
    Returns (df, spot, is_live: bool).
    """
    if use_live:
        try:
            df, spot = fetch_option_chain(symbol)
            return df, spot, True
        except Exception:
            pass
    df, spot = sample_option_chain(symbol)
    return df, spot, False


if __name__ == "__main__":
    for sym in ("NIFTY", "BANKNIFTY"):
        df, spot, is_live = get_chain(sym)
        print(f"{sym} | Live data: {is_live} | Spot: {spot}")
        print(df.head())
