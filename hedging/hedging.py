"""
The hedging arithmetic. Everything else in the project is built on these
few formulas, so they are written out explicitly.

For one foreign asset over one period (simple returns, decimals):

    unhedged return in CHF   R_U = (1 + r_local) * (1 + r_fx) - 1

A Swiss investor hedges by SELLING the foreign currency forward at the start
of the period, for an amount equal to the value of the position. Per franc
invested, the forward pays

    hedge P&L                H = fwd_prem - r_fx

(it gains when the foreign currency falls, and it earns/pays the interest-rate
differential fwd_prem). With a hedge ratio h (0 = no hedge, 1 = full hedge):

    R(h) = R_U + h * H

The minimum-variance hedge ratio minimises Var(R_U + h * H):

    h* = Cov(R_U, -H) / Var(H)  = slope of a regression of R_U on (r_fx - fwd_prem)

and the R-squared of that regression is the share of the variance that the
best hedge removes.
"""
import numpy as np
import pandas as pd

from . import config
from .econometrics import ols_nw, rolling_beta

PORT = "PORT"


def asset_streams(df, weights=config.PORTFOLIO):
    """
    For every asset (and the portfolio): unhedged CHF return and hedge P&L.
    Returns a dict  name -> DataFrame with columns R_U, H, r_local, r_fx, rf.
    """
    streams = {}
    for name, spec in config.ASSETS.items():
        ccy = spec["currency"]
        r_local, r_fx = df[f"r_local_{name}"], df[f"r_fx_{ccy}"]
        streams[name] = pd.DataFrame({
            "R_U": (1 + r_local) * (1 + r_fx) - 1,
            "H": df[f"fwd_prem_{ccy}"] - r_fx,
            "r_local": r_local,
            "r_fx": r_fx,
            "rf": df["rf_CHF"],
        })
    # Portfolio rebalanced to fixed weights every period, same hedge ratio on
    # every asset: both the return and the hedge P&L are weighted sums
    port = sum(w * streams[name] for name, w in weights.items())
    streams[PORT] = port
    return streams


def hedged_return(stream, h):
    """R(h) = R_U + h * H."""
    return stream["R_U"] + h * stream["H"]


def min_variance_hedge(stream, sample=None):
    """
    h* from OLS of R_U on X = -H (with a constant), Newey-West standard errors.
    Reports tests of h* = 0 (no hedge) and h* = 1 (full hedge).
    """
    d = stream if sample is None else stream.loc[sample]
    data = pd.DataFrame({"R_U": d["R_U"], "X": -d["H"]})
    res = ols_nw(data, "R_U", ["X"])
    test_one = res.t_test("X = 1")
    h = res.params["X"]
    return {
        "h_star": h, "se": res.bse["X"],
        "ci_low": h - 1.96 * res.bse["X"], "ci_high": h + 1.96 * res.bse["X"],
        "p_h_eq_0": res.pvalues["X"], "p_h_eq_1": float(test_one.pvalue),
        "r2": res.rsquared, "n": int(res.nobs),
        "start": data.index.min().date(), "end": data.index.max().date(),
    }


def vol_curve(stream, grid, periods_per_year=config.PERIODS_PER_YEAR):
    """Annualised volatility of R(h) for every hedge ratio h in `grid`."""
    return pd.Series([hedged_return(stream, h).std() * np.sqrt(periods_per_year)
                      for h in grid], index=grid)


def rolling_hedge_ratio(stream, window=config.ROLLING_MONTHS):
    """h* over a rolling window (estimate at date t uses periods t-window+1..t)."""
    data = pd.DataFrame({"R_U": stream["R_U"], "X": -stream["H"]})
    return rolling_beta(data, "R_U", "X", window=window, min_obs=window)


def out_of_sample_hedge(stream, window=config.ROLLING_MONTHS, bounds=(0.0, 1.0)):
    """
    A rule an investor could have followed in real time: each period, use the
    h* estimated on the previous `window` periods only, kept inside `bounds`
    (no over-hedging, no speculative long currency position).
    Returns the hedge ratio used and the realised return.
    """
    h_used = rolling_hedge_ratio(stream, window)["beta"].shift(1).clip(*bounds)
    r = stream["R_U"] + h_used * stream["H"]
    return pd.DataFrame({"h_used": h_used, "R": r}).dropna()
