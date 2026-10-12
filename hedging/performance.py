"""
Performance statistics for a series of simple periodic returns (decimals).
"""
import numpy as np
import pandas as pd

from . import config


def cagr(r, periods_per_year=config.PERIODS_PER_YEAR):
    """Compound annual growth rate: (prod(1 + r))^(periods_per_year / n) - 1."""
    return (1 + r).prod() ** (periods_per_year / len(r)) - 1


def ann_vol(r, periods_per_year=config.PERIODS_PER_YEAR):
    """Annualised volatility: standard deviation * sqrt(periods per year)."""
    return r.std() * np.sqrt(periods_per_year)


def sharpe(r, rf, periods_per_year=config.PERIODS_PER_YEAR):
    """Annualised Sharpe ratio of returns in excess of the CHF short rate."""
    ex = r - rf
    return ex.mean() / ex.std() * np.sqrt(periods_per_year)


def max_drawdown(r):
    """Largest peak-to-trough fall of the wealth path, starting from 1."""
    wealth = pd.concat([pd.Series([1.0]), (1 + r).cumprod().reset_index(drop=True)])
    return (wealth / wealth.cummax() - 1).min()


def summary(r, rf, periods_per_year=config.PERIODS_PER_YEAR):
    return {
        "cagr": cagr(r, periods_per_year),
        "vol": ann_vol(r, periods_per_year),
        "sharpe": sharpe(r, rf, periods_per_year),
        "max_dd": max_drawdown(r),
        "worst": r.min(),
        "worst_date": r.idxmin().date(),
    }
