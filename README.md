# Options Greeks Dashboard
A Black-Scholes-based options Greeks dashboard for NIFTY / BANKNIFTY, built as an S&amp;T interview portfolio project. Live NSE option chain data with a deterministic sample-data fallback for offline/demo use.
Features
Chain View — Delta, Gamma, Theta, Vega for calls and puts across the full strike chain, plus a plot of any Greek vs. strike (smile-shaped curves).
Single Option — Deep-dive on one strike/type: theoretical price, all five Greeks, IV backed out from the live LTP via Newton-Raphson, and a payoff diagram.
Portfolio Builder — Add multiple legs (e.g. Buy Call + Buy Put = long straddle) and see aggregated net Delta/Gamma/Theta/Vega/Rho — this is the same shape of risk view used on a live trading desk — plus a combined P&L-at-expiry chart.
Setup
bash
pip install -r requirements.txt
streamlit run app.py
Data
Attempts a live pull from NSE's option chain API via nsepython.
NSE aggressively rate-limits/blocks non-browser and many cloud/hosted IPs, so if the live fetch fails, the app falls back to a sample chain automatically (clearly labeled in the sidebar: 🟢 live vs 🟡 sample) so the dashboard is always demoable.
Run locally (laptop/college wifi) for the best shot at live data; a hosted demo will likely show sample data — that's expected and disclosed in-app.
Methodology notes (for interviews)
Pricing: standard Black-Scholes-Merton, no early exercise (reasonable for European-style NSE index options).
Greeks are reported in trader-convention units: Theta per calendar day, Vega per 1 vol point, Rho per 1% rate move.
IV solved via Newton-Raphson with a bisection fallback for cases where Newton fails to converge (deep ITM/OTM, near-expiry).
Risk-free rate is a manual input (default ~6.5%, proxying the short-end India T-bill rate) — flagged as a simplification; a real desk would use a proper OIS/MIBOR curve.
No dividend yield adjustment needed for index options (q=0 by default, though the pricing functions support q for extensibility to stock options).
Possible extensions
Pull a real risk-free curve instead of a flat manual rate.
Add an IV surface (strike x expiry) heatmap.
Historical Greeks tracking (save daily snapshots, chart Theta decay over the option's life).
Connect to this project's macro/FX CIRP dashboard for a unified risk view.
