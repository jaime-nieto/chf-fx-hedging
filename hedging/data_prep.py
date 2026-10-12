"""
From raw daily/monthly series to one table of period returns (monthly by default).

Conventions (all returns are SIMPLE returns, as decimals: 0.01 = 1%):
- r_local   return of the asset in its own currency (USD or EUR)
- r_fx      change in the franc price of one unit of foreign currency:
            r_fx > 0  ->  the dollar/euro gained against the franc
            (good news for an unhedged Swiss investor)
- fwd_prem  forward premium (F/S - 1) of a forward contract that sells the
            foreign currency for francs, from covered interest parity:
            (1 + i_CHF * dt) / (1 + i_foreign * dt) - 1.
            Negative when CHF rates are below foreign rates: that is the cost
            of hedging.
- rates are the value for the month BEFORE the period starts, so a hedge
  only uses information available when it is put on.
"""
import numpy as np
import pandas as pd

from . import config
from .data_download import load_raw

PERIOD_RULE = {"M": "ME", "Q": "QE"}
PERIOD_DT = {"M": 1 / 12, "Q": 1 / 4}


def period_end(series, freq="M"):
    """Last available value of each month (or quarter)."""
    return series.resample(PERIOD_RULE[freq]).last()


def bond_return(y_prev, y_now, maturity=config.BOND_MATURITY, dt=1 / 12):
    """
    Return over one period of a government bond bought at par.

    At the start of the period we buy a `maturity`-year bond whose annual
    coupon equals the yield at that moment (y_prev), so it costs 1 (par).
    At the end of the period we have earned one period of coupon and the bond,
    now with maturity - dt years left, is priced at the new yield y_now:

        price = c / y * (1 - (1 + y)^-n) + (1 + y)^-n,   c = y_prev, y = y_now
        return = coupon * dt + price - 1

    Yields in % per year. Works with zero and negative yields.
    """
    c = np.asarray(y_prev, dtype=float) / 100
    y = np.asarray(y_now, dtype=float) / 100
    n = maturity - dt
    discount = (1 + y) ** (-n)
    # annuity factor (1 - discount) / y; its limit when y -> 0 is n
    safe_y = np.where(np.abs(y) < 1e-10, 1.0, y)
    annuity = np.where(np.abs(y) < 1e-10, n, (1 - discount) / safe_y)
    price = c * annuity + discount
    return c * dt + price - 1


def forward_premium(rate_chf, rate_foreign, dt):
    """F/S - 1 for selling foreign currency forward (covered interest parity)."""
    return (1 + rate_chf / 100 * dt) / (1 + rate_foreign / 100 * dt) - 1


RATE_SERIES = ["RATE_CHF", "RATE_USD", "RATE_EUR"]


def missing_rate_months():
    """Months with no published value inside each rate series (data check)."""
    out = {}
    for name in RATE_SERIES:
        s = load_raw(name)
        full = pd.date_range(s.index.min(), s.index.max(), freq="MS")
        out[name] = list(full.difference(s.index).strftime("%Y-%m"))
    return out


def load_monthly_rates():
    """
    Monthly short rates (% p.a.) indexed by the last day of their month.
    A single missing month is filled with the previous month's value (the
    latest information an investor would have had); see missing_rate_months().
    """
    rates = pd.concat([load_raw(n) for n in RATE_SERIES], axis=1)
    full = pd.date_range(rates.index.min(), rates.index.max(), freq="MS")
    rates = rates.reindex(full).ffill(limit=1)
    rates.index = rates.index + pd.offsets.MonthEnd(0)
    return rates


def build_returns(freq="M", usdchf_source="ecb"):
    """
    One row per period with local returns, FX returns, forward premia and the
    CHF risk-free rate. `usdchf_source="fed"` swaps the ECB cross rate for the
    Fed H.10 series (robustness).
    """
    dt = PERIOD_DT[freq]
    px = pd.concat([period_end(load_raw(n), freq) for n in
                    ["EURCHF", "EURUSD", "USDCHF_FED", "SPX_TR", "DAX", "UST10Y", "BUND10Y"]],
                   axis=1)
    if usdchf_source == "ecb":
        px["USDCHF"] = px["EURCHF"] / px["EURUSD"]     # same 14:15 CET fixing
    else:
        px["USDCHF"] = px["USDCHF_FED"]

    out = pd.DataFrame(index=px.index)
    # Local-currency returns of the four foreign assets
    out["r_local_US_EQ"] = px["SPX_TR"].pct_change()
    out["r_local_DE_EQ"] = px["DAX"].pct_change()
    out["r_local_US_BD"] = bond_return(px["UST10Y"].shift(1), px["UST10Y"], dt=dt)
    out["r_local_DE_BD"] = bond_return(px["BUND10Y"].shift(1), px["BUND10Y"], dt=dt)
    # Currency returns, seen from Switzerland (CHF per unit of foreign currency)
    out["r_fx_USD"] = px["USDCHF"].pct_change()
    out["r_fx_EUR"] = px["EURCHF"].pct_change()

    # Rates known at the start of the period = value of the previous month
    rates = load_monthly_rates().reindex(px.index).shift(1)
    out["rate_CHF"], out["rate_USD"], out["rate_EUR"] = (
        rates["RATE_CHF"], rates["RATE_USD"], rates["RATE_EUR"])
    out["fwd_prem_USD"] = forward_premium(rates["RATE_CHF"], rates["RATE_USD"], dt)
    out["fwd_prem_EUR"] = forward_premium(rates["RATE_CHF"], rates["RATE_EUR"], dt)
    out["rf_CHF"] = rates["RATE_CHF"] / 100 * dt

    out["floor_period"] = (out.index >= config.FLOOR_START) & (out.index <= config.FLOOR_END)
    out = out.loc[config.SAMPLE_START:config.SAMPLE_END]
    if out.drop(columns="floor_period").isna().any().any():
        missing = out.columns[out.isna().any()].tolist()
        raise ValueError(f"Missing values in {missing}; check the data cache.")
    return out
