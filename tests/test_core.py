"""
Unit tests for the formulas the whole project relies on.
They use synthetic data only, so they run without the data cache.

    python -m pytest -q
"""
import numpy as np
import pandas as pd
import pytest

from hedging import data_prep as dp
from hedging import hedging as hg
from hedging import performance as pf
from hedging.econometrics import newey_west_lags, ols_nw


# --- Forward premium and hedge arithmetic -------------------------------------
def test_forward_premium_is_zero_when_rates_are_equal():
    assert dp.forward_premium(2.0, 2.0, 1 / 12) == pytest.approx(0.0)


def test_forward_premium_is_negative_when_chf_rates_are_lower():
    fp = dp.forward_premium(0.0, 3.0, 1 / 12)      # CHF 0%, USD 3%
    assert fp < 0
    assert fp == pytest.approx(-0.03 / 12, rel=0.01)   # about -0.25% per month


def test_full_hedge_removes_the_currency_move():
    # Asset +5% in USD, dollar -10% against the franc, no carry
    df = pd.DataFrame({"r_local_US_EQ": [0.05], "r_fx_USD": [-0.10], "fwd_prem_USD": [0.0],
                       "r_local_US_BD": [0.0], "r_local_DE_EQ": [0.0], "r_local_DE_BD": [0.0],
                       "r_fx_EUR": [0.0], "fwd_prem_EUR": [0.0], "rf_CHF": [0.0]})
    s = hg.asset_streams(df)["US_EQ"]
    assert s["R_U"].iloc[0] == pytest.approx(1.05 * 0.90 - 1)           # -5.5% unhedged
    assert s["H"].iloc[0] == pytest.approx(0.10)                        # hedge gains 10%
    # Fully hedged: the local return, minus the unhedged currency effect on the gain
    assert hg.hedged_return(s, 1.0).iloc[0] == pytest.approx(0.05 - 0.05 * 0.10)


def test_portfolio_is_the_weighted_sum_of_assets():
    rng = np.random.default_rng(0)
    cols = ["r_local_US_EQ", "r_local_US_BD", "r_local_DE_EQ", "r_local_DE_BD",
            "r_fx_USD", "r_fx_EUR", "fwd_prem_USD", "fwd_prem_EUR", "rf_CHF"]
    df = pd.DataFrame(rng.normal(0, 0.02, (50, len(cols))), columns=cols)
    weights = {"US_EQ": 0.3, "DE_EQ": 0.3, "US_BD": 0.2, "DE_BD": 0.2}
    st = hg.asset_streams(df, weights)
    expected = sum(w * hg.hedged_return(st[k], 0.5) for k, w in weights.items())
    assert np.allclose(hg.hedged_return(st["PORT"], 0.5), expected)


# --- Bond returns from yields --------------------------------------------------
@pytest.mark.parametrize("y", [3.0, 0.0, -0.5])
def test_bond_return_with_unchanged_yield_is_one_month_of_coupon(y):
    assert dp.bond_return(y, y) == pytest.approx(y / 100 / 12)


def test_bond_loses_about_its_duration_when_yields_rise():
    r = dp.bond_return(3.0, 4.0)          # +100 bp on a 10-year bond at 3%
    assert -0.09 < r < -0.07              # duration of a 10y par bond at 3% is ~8.5


# --- Data alignment: month-end prices and lagged rates ------------------------
def test_build_returns_uses_last_month_rates_and_ecb_cross(monkeypatch):
    days = pd.bdate_range("1999-07-01", "2026-09-30")
    months = pd.date_range("1999-07-01", "2026-09-01", freq="MS")
    fake = {name: pd.Series(1.0, index=days, name=name)
            for name in ["EURCHF", "EURUSD", "USDCHF_FED", "SPX_TR", "DAX"]}
    fake["UST10Y"] = pd.Series(3.0, index=days, name="UST10Y")
    fake["BUND10Y"] = pd.Series(2.0, index=days, name="BUND10Y")
    # EUR/USD jumps from 1.0 to 1.25 at the end of February 2000 -> USD/CHF falls 20%
    fake["EURUSD"].loc["2000-02-29":] = 1.25
    fake["RATE_CHF"] = pd.Series(0.0, index=months, name="RATE_CHF")
    fake["RATE_EUR"] = pd.Series(1.0, index=months, name="RATE_EUR")
    fake["RATE_USD"] = pd.Series(np.arange(len(months), dtype=float) % 5, index=months,
                                 name="RATE_USD")
    monkeypatch.setattr(dp, "load_raw", lambda name: fake[name])

    df = dp.build_returns("M")
    jan_usd_rate = fake["RATE_USD"].loc["2000-01-01"]
    assert df.loc["2000-02-29", "rate_USD"] == jan_usd_rate          # January rate in February
    assert df.loc["2000-02-29", "fwd_prem_USD"] == pytest.approx(
        1 / (1 + jan_usd_rate / 100 / 12) - 1)
    assert df.loc["2000-02-29", "r_fx_USD"] == pytest.approx(1 / 1.25 - 1)
    assert df.loc["2000-02-29", "r_fx_EUR"] == pytest.approx(0.0)
    assert df.loc["2000-03-31", "r_local_US_BD"] == pytest.approx(0.03 / 12)


def test_single_missing_rate_month_is_filled_with_previous_value(monkeypatch):
    months = pd.date_range("2020-01-01", periods=4, freq="MS")
    fake = {"RATE_CHF": pd.Series([0.0] * 4, months),
            "RATE_EUR": pd.Series([1.0] * 4, months),
            "RATE_USD": pd.Series([1.5, 1.0, 0.5], months.delete(2))}   # March missing
    monkeypatch.setattr(dp, "load_raw", lambda name: fake[name].rename(name))
    rates = dp.load_monthly_rates()
    assert rates.loc["2020-03-31", "RATE_USD"] == 1.0
    assert dp.missing_rate_months()["RATE_USD"] == ["2020-03"]


# --- Hedge ratio estimators -----------------------------------------------------
@pytest.fixture
def simulated_stream():
    rng = np.random.default_rng(1)
    n = 2000
    x = rng.normal(0, 0.03, n)                     # currency return net of carry
    r_u = 0.004 + 0.7 * x + rng.normal(0, 0.03, n)
    idx = pd.date_range("2000-01-31", periods=n, freq="ME")
    return pd.DataFrame({"R_U": r_u, "H": -x, "rf": 0.0}, index=idx)


def test_min_variance_hedge_recovers_true_ratio(simulated_stream):
    m = hg.min_variance_hedge(simulated_stream)
    assert m["h_star"] == pytest.approx(0.7, abs=0.05)
    assert m["p_h_eq_1"] < 0.01


def test_volatility_curve_is_lowest_near_h_star(simulated_stream):
    grid = np.round(np.arange(0, 2.0001, 0.01), 2)
    curve = hg.vol_curve(simulated_stream, grid)
    h = hg.min_variance_hedge(simulated_stream)["h_star"]
    assert abs(curve.idxmin() - h) <= 0.01


def test_out_of_sample_rule_only_uses_past_data(simulated_stream):
    s = simulated_stream.iloc[:200]
    oos = hg.out_of_sample_hedge(s, window=60, bounds=(-10, 10))
    t = s.index[100]
    past = s.loc[s.index[40]:s.index[99]]             # the 60 months before t
    data = pd.DataFrame({"R_U": past["R_U"], "X": -past["H"]})
    assert oos.loc[t, "h_used"] == pytest.approx(ols_nw(data, "R_U", ["X"]).params["X"])


# --- Performance statistics ------------------------------------------------------
def test_max_drawdown_counts_a_first_month_loss():
    assert pf.max_drawdown(pd.Series([-0.2, 0.1])) == pytest.approx(-0.2)
    assert pf.max_drawdown(pd.Series([0.1, -0.5, 0.2])) == pytest.approx(-0.5)


def test_cagr_of_constant_monthly_return():
    r = pd.Series([0.01] * 24)
    assert pf.cagr(r) == pytest.approx(1.01 ** 12 - 1)


def test_newey_west_lag_rule():
    assert newey_west_lags(100) == 4
    assert newey_west_lags(321) == 5
