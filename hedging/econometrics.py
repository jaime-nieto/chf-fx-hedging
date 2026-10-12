"""
Econometric tools, kept deliberately simple.

Everything is ordinary least squares (OLS). The only refinement is in the
standard errors: monthly returns show volatility clustering (heteroskedasticity)
and some autocorrelation, which makes the textbook OLS standard errors too
optimistic. Newey-West (HAC) standard errors are robust to both, so every
t-statistic and p-value in the project uses them.
"""
import numpy as np
import pandas as pd
import statsmodels.api as sm


def newey_west_lags(n_obs):
    """Rule of thumb for the number of lags: floor(4 * (n/100)^(2/9))."""
    return int(np.floor(4 * (n_obs / 100) ** (2 / 9)))


def ols_nw(data, y, xs, constant=True):
    """OLS of `y` on `xs` (plus a constant) with Newey-West standard errors."""
    d = data[[y] + list(xs)].dropna()
    X = sm.add_constant(d[list(xs)]) if constant else d[list(xs)]
    lags = newey_west_lags(len(d))
    return sm.OLS(d[y], X).fit(cov_type="HAC", cov_kwds={"maxlags": lags})


def mean_test(series):
    """Mean of a series with a Newey-West t-test of mean = 0."""
    data = pd.DataFrame({"y": series}).dropna()
    data["one"] = 1.0
    res = ols_nw(data, "y", ["one"], constant=False)
    return {"mean": res.params["one"], "se": res.bse["one"], "t": res.tvalues["one"],
            "p": res.pvalues["one"], "n": int(res.nobs)}


def rolling_beta(data, y, x, window, min_obs):
    """
    Beta of y on x over a rolling window: beta = cov(y, x) / var(x).
    Also returns the textbook OLS standard error of the slope,
    se = sqrt((1 - rho^2) / (n - 2)) * sd(y) / sd(x), used for the bands
    in the charts (bands are indicative: overlapping windows, no HAC).
    """
    d = data[[y, x]].copy()
    d[d.isna().any(axis=1)] = np.nan          # keep the same periods for y and x
    roll_y = d[y].rolling(window, min_periods=min_obs)
    roll_x = d[x].rolling(window, min_periods=min_obs)
    beta = roll_y.cov(d[x]) / roll_x.var()
    rho = roll_y.corr(d[x])
    n = roll_x.count()
    se = np.sqrt((1 - rho**2) / (n - 2)) * roll_y.std() / roll_x.std()
    return pd.DataFrame({"beta": beta, "se": se, "n": n})
