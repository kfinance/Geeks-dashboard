"""
greeks.py
Black-Scholes-Merton pricing and option Greeks for European options
(Nifty / Bank Nifty index options — no dividends, so BSM without a
continuous dividend yield is a reasonable approximation; a q term is
included anyway for generality / equity underlyings).

All Greeks are returned in "trader" units:
  - Delta: unitless (0 to 1 for calls, -1 to 0 for puts)
  - Gamma: change in delta per 1.00 move in spot
  - Theta: value decay PER DAY (not per year)
  - Vega:  change in price per 1.00 (100 percentage points) move in IV,
           then divided by 100 so it reads as "price change per 1 vol point"
  - Rho:   change in price per 1.00 (100 percentage points) move in
           rate, divided by 100 so it reads as "price change per 1% rate move"
"""

import numpy as np
from scipy.stats import norm

def _d1_d2(S, K, T, r, sigma, q=0.0):
    """Core BSM intermediate terms. T in years, sigma annualized."""
    if T <= 0 or sigma <= 0:
        # At/after expiry or degenerate vol -> avoid div by zero
        T = max(T, 1e-6)
        sigma = max(sigma, 1e-6)
    d1 = (np.log(S / K) + (r - q + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    return d1, d2


def bs_price(S, K, T, r, sigma, option_type="call", q=0.0):
    """Theoretical Black-Scholes price."""
    d1, d2 = _d1_d2(S, K, T, r, sigma, q)
    if option_type == "call":
        price = S * np.exp(-q * T) * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
    else:
        price = K * np.exp(-r * T) * norm.cdf(-d2) - S * np.exp(-q * T) * norm.cdf(-d1)
    return price


def delta(S, K, T, r, sigma, option_type="call", q=0.0):
    d1, _ = _d1_d2(S, K, T, r, sigma, q)
    if option_type == "call":
        return np.exp(-q * T) * norm.cdf(d1)
    else:
        return -np.exp(-q * T) * norm.cdf(-d1)


def gamma(S, K, T, r, sigma, q=0.0):
    d1, _ = _d1_d2(S, K, T, r, sigma, q)
    T = max(T, 1e-6)
    return np.exp(-q * T) * norm.pdf(d1) / (S * sigma * np.sqrt(T))


def theta(S, K, T, r, sigma, option_type="call", q=0.0):
    d1, d2 = _d1_d2(S, K, T, r, sigma, q)
    T_safe = max(T, 1e-6)
    term1 = -(S * np.exp(-q * T_safe) * norm.pdf(d1) * sigma) / (2 * np.sqrt(T_safe))
    if option_type == "call":
        term2 = -r * K * np.exp(-r * T_safe) * norm.cdf(d2)
        term3 = q * S * np.exp(-q * T_safe) * norm.cdf(d1)
        annual_theta = term1 + term2 + term3
    else:
        term2 = r * K * np.exp(-r * T_safe) * norm.cdf(-d2)
        term3 = -q * S * np.exp(-q * T_safe) * norm.cdf(-d1)
        annual_theta = term1 + term2 + term3
    return annual_theta / 365.0  # per calendar day


def vega(S, K, T, r, sigma, q=0.0):
    d1, _ = _d1_d2(S, K, T, r, sigma, q)
    T_safe = max(T, 1e-6)
    v = S * np.exp(-q * T_safe) * norm.pdf(d1) * np.sqrt(T_safe)
    return v / 100.0  # per 1 vol point (e.g. IV 20% -> 21%)


def rho(S, K, T, r, sigma, option_type="call", q=0.0):
    _, d2 = _d1_d2(S, K, T, r, sigma, q)
    T_safe = max(T, 1e-6)
    if option_type == "call":
        r_val = K * T_safe * np.exp(-r * T_safe) * norm.cdf(d2)
    else:
        r_val = -K * T_safe * np.exp(-r * T_safe) * norm.cdf(-d2)
    return r_val / 100.0  # per 1% rate move


def all_greeks(S, K, T, r, sigma, option_type="call", q=0.0):
    """Convenience wrapper: price + all Greeks in one dict."""
    return {
        "price": bs_price(S, K, T, r, sigma, option_type, q),
        "delta": delta(S, K, T, r, sigma, option_type, q),
        "gamma": gamma(S, K, T, r, sigma, q),
        "theta": theta(S, K, T, r, sigma, option_type, q),
        "vega": vega(S, K, T, r, sigma, q),
        "rho": rho(S, K, T, r, sigma, option_type, q),
    }


def implied_volatility(market_price, S, K, T, r, option_type="call", q=0.0,
                        tol=1e-6, max_iter=100):
    """
    Solve for IV given a market price using Newton-Raphson with a
    bisection fallback (Newton can misbehave for deep ITM/OTM or near
    expiry, which happens a lot with real NSE quotes).
    """
    if T <= 0 or market_price <= 0:
        return np.nan

    # Newton-Raphson
    sigma = 0.25
    for _ in range(max_iter):
        price = bs_price(S, K, T, r, sigma, option_type, q)
        v = vega(S, K, T, r, sigma, q) * 100  # undo the /100 scaling
        diff = market_price - price
        if abs(diff) < tol:
            return sigma
        if v < 1e-8:
            break
        sigma = sigma + diff / v
        if sigma <= 0 or sigma > 5:
            break
    # Newton didn't converge within tol (whether it broke out early or
    # simply ran out of iterations) — fall through to bisection below
    # rather than returning an un-converged sigma silently.

    # Bisection fallback
    lo, hi = 1e-4, 5.0
    for _ in range(200):
        mid = (lo + hi) / 2
        price = bs_price(S, K, T, r, mid, option_type, q)
        if abs(price - market_price) < tol:
            return mid
        if price > market_price:
            hi = mid
        else:
            lo = mid
    return mid


if __name__ == "__main__":
    # Quick sanity check against a known textbook-style example
    S, K, T, r, sigma = 100, 100, 0.5, 0.05, 0.20
    print("ATM Call:", all_greeks(S, K, T, r, sigma, "call"))
    print("ATM Put:", all_greeks(S, K, T, r, sigma, "put"))
