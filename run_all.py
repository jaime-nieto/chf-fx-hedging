"""
Run the whole project: download (or read cached) data, build monthly returns,
produce every table and figure, and write results/summary.md.

    python run_all.py            # uses data/raw/ if present, downloads the rest
    python run_all.py --refresh  # re-download everything

Each step below matches a section of the README.
"""
import argparse
import json

import numpy as np
import pandas as pd

from hedging import config, plotting
from hedging import data_prep as dp
from hedging import hedging as hg
from hedging import performance as pf
from hedging.data_download import download_all, load_raw
from hedging.econometrics import mean_test, ols_nw
from hedging.reporting import pct, save_table, stars, write_summary

NAMES = plotting.NAMES
ORDER = plotting.ORDER
PPY = config.PERIODS_PER_YEAR
H_LABEL = {0.0: "h = 0", 0.5: "h = 0.5", 1.0: "h = 1"}


def fmt_h(m):
    """'0.70 [0.48, 0.92]'"""
    return f"{m['h_star']:.2f} [{m['ci_low']:.2f}, {m['ci_high']:.2f}]"


# ---------------------------------------------------------------------------
# Step 0. Data checks
# ---------------------------------------------------------------------------
def step0_data_checks(df):
    print("Step 0: data checks")
    manifest = json.loads((config.RAW_DIR / "manifest.json").read_text())
    cov = pd.DataFrame([{"series": k, "source": v["source"], "code": v["code"],
                         "first": v["first_date"], "last": v["last_date"], "obs": v["n_obs"]}
                        for k, v in manifest.items()])
    save_table("t0a_data_coverage", "Table 0a. Data series in the cache", cov)

    # Bond returns rebuilt from yields vs bond ETFs (prices adjusted for distributions)
    rows = []
    for asset, etf in [("US_BD", "ETF_UST"), ("DE_BD", "ETF_BUND")]:
        etf_r = dp.period_end(load_raw(etf)).pct_change()
        d = pd.DataFrame({"built": df[f"r_local_{asset}"], "etf": etf_r}).dropna()
        d = d.iloc[1:]                       # first ETF month is incomplete
        beta = ols_nw(d, "etf", ["built"]).params["built"]
        rows.append({"bond": NAMES[asset], "etf": config.SERIES[etf]["code"],
                     "start": d.index.min().date(), "end": d.index.max().date(), "months": len(d),
                     "correlation": d["built"].corr(d["etf"]), "beta_etf_on_built": beta,
                     "ann_return_built": pf.cagr(d["built"]), "ann_return_etf": pf.cagr(d["etf"]),
                     "vol_built": pf.ann_vol(d["built"]), "vol_etf": pf.ann_vol(d["etf"])})
    raw = pd.DataFrame(rows)
    pretty = raw.assign(
        correlation=raw.correlation.map("{:.3f}".format),
        beta_etf_on_built=raw.beta_etf_on_built.map("{:.2f}".format),
        **{c: raw[c].map(pct) for c in ["ann_return_built", "ann_return_etf", "vol_built", "vol_etf"]})
    save_table("t0b_bond_validation",
               "Table 0b. Bond returns built from 10-year yields vs bond ETFs (monthly)",
               pretty, raw,
               note="The ETFs hold a range of maturities (7-10y and 5.5-10.5y, i.e. shorter on "
                    "average than our single 10-year bond), charge fees and hold actual bonds "
                    "rather than a fitted yield, so their volatility, beta and return differ. "
                    "The check is that the month-to-month movements match (correlation).")

    # USD/CHF: ECB cross rate vs Fed H.10
    fed = dp.build_returns("M", usdchf_source="fed")["r_fx_USD"]
    diff = (df["r_fx_USD"] - fed).abs()
    fx = pd.DataFrame([{"correlation": df["r_fx_USD"].corr(fed),
                        "mean_abs_diff": diff.mean(), "max_abs_diff": diff.max(),
                        "max_diff_month": diff.idxmax().date(), "months": len(diff)}])
    save_table("t0c_usdchf_sources",
               "Table 0c. Monthly USD/CHF returns: ECB cross rate vs Fed H.10",
               fx.assign(correlation=fx.correlation.map("{:.4f}".format),
                         mean_abs_diff=fx.mean_abs_diff.map(lambda v: pct(v, 2)),
                         max_abs_diff=fx.max_abs_diff.map(lambda v: pct(v, 2))), fx,
               note="The ECB fixes at 14:15 CET and the Fed at noon New York, so month-end "
                    "values differ by a few hours of trading.")

    # Does the total-return index really include dividends?
    spx = dp.period_end(load_raw("SPX")).pct_change().loc[df.index]
    divs = pd.DataFrame([{"cagr_SP500_TR": pf.cagr(df["r_local_US_EQ"]), "cagr_SP500_price": pf.cagr(spx)}])
    divs["difference"] = divs.cagr_SP500_TR - divs.cagr_SP500_price
    save_table("t0d_dividends", "Table 0d. S&P 500 total-return vs price index, 2000-2026",
               divs.map(lambda v: pct(v, 2)), divs,
               note="The difference should be roughly the average dividend yield.")

    # Largest monthly moves (to spot data errors)
    rows = []
    for col in [c for c in df.columns if c.startswith(("r_local_", "r_fx_"))]:
        top = df[col].abs().nlargest(3).index
        for d in top:
            rows.append({"series": col, "month": d.strftime("%Y-%m"), "return": df.loc[d, col]})
    raw = pd.DataFrame(rows)
    save_table("t0e_largest_moves", "Table 0e. The three largest monthly moves of each series",
               raw.assign(**{"return": raw["return"].map(pct)}), raw,
               note="Listed to spot data errors. They fall in well-known stress months "
                    "(e.g. Oct 2008, Aug 2011, Jan 2015, Mar 2020) rather than in quiet periods.")

    gaps = dp.missing_rate_months()
    save_table("t0f_rate_gaps", "Table 0f. Months missing in the short-rate series",
               pd.DataFrame([{"series": k, "missing months": ", ".join(v) or "none"}
                             for k, v in gaps.items()]),
               note="A missing month is filled with the previous month's value.")


# ---------------------------------------------------------------------------
# Step 1. Where does the risk come from?
# ---------------------------------------------------------------------------
def step1_components(df, streams):
    print("Step 1: risk decomposition")
    rows = []
    for name in ORDER:
        s = streams[name]
        rows.append({"asset": NAMES[name],
                     "vol_local": pf.ann_vol(s["r_local"]),
                     "vol_fx": pf.ann_vol(s["r_fx"]),
                     "corr_local_fx": s["r_local"].corr(s["r_fx"]),
                     "vol_unhedged": pf.ann_vol(hg.hedged_return(s, 0.0)),
                     "vol_hedged": pf.ann_vol(hg.hedged_return(s, 1.0))})
    raw = pd.DataFrame(rows)
    raw["vol_change"] = raw.vol_hedged / raw.vol_unhedged - 1
    pretty = raw.copy()
    for c in ["vol_local", "vol_fx", "vol_unhedged", "vol_hedged", "vol_change"]:
        pretty[c] = raw[c].map(pct)
    pretty["corr_local_fx"] = raw.corr_local_fx.map("{:.2f}".format)
    save_table("t1_risk_decomposition",
               "Table 1. Volatility in local currency, of the currency, and in francs (annualised)",
               pretty, raw,
               note="corr_local_fx < 0 means the foreign currency tends to rise against the franc "
                    "when the asset falls (a natural hedge). For the portfolio, vol_fx is the "
                    "volatility of the 50/50 USD-EUR currency basket.")


# ---------------------------------------------------------------------------
# Step 2. Performance of the three static rules
# ---------------------------------------------------------------------------
def step2_performance(streams):
    print("Step 2: performance by hedge ratio")
    rows = []
    for name in ORDER:
        s = streams[name]
        for h in config.HEDGE_RATIOS:
            rows.append({"asset": NAMES[name], "hedge": H_LABEL[h],
                         **pf.summary(hg.hedged_return(s, h), s["rf"])})
    raw = pd.DataFrame(rows)
    pretty = raw.assign(cagr=raw.cagr.map(pct), vol=raw.vol.map(pct),
                        sharpe=raw.sharpe.map("{:.2f}".format), max_dd=raw.max_dd.map(pct),
                        worst=raw.worst.map(pct),
                        worst_date=raw.worst_date.map(lambda d: d.strftime("%Y-%m")))
    save_table("t2_performance", "Table 2. Performance in francs, Jan 2000 - Sep 2026",
               pretty, raw,
               note="cagr = compound annual return; vol = annualised volatility; sharpe = "
                    "annualised mean return in excess of the CHF 3-month rate / volatility; "
                    "max_dd = largest peak-to-trough loss; worst = worst single month.")
    plotting.plot_wealth(streams, hg.hedged_return)


# ---------------------------------------------------------------------------
# Step 3. The cost of hedging
# ---------------------------------------------------------------------------
def step3_cost(df):
    print("Step 3: cost of hedging")
    periods = [(config.SAMPLE_START, config.SAMPLE_END, "Full sample")] + config.SUBPERIODS
    rows = []
    for ccy in ["USD", "EUR"]:
        carry, fx = df[f"fwd_prem_{ccy}"], df[f"r_fx_{ccy}"]
        for start, end, label in periods:
            hedge = (carry - fx).loc[start:end]
            t = mean_test(hedge)
            rows.append({"currency": ccy, "period": label,
                         "carry_ann": PPY * carry.loc[start:end].mean(),
                         "fx_return_ann": PPY * fx.loc[start:end].mean(),
                         "hedge_pnl_ann": PPY * t["mean"], "t": t["t"], "p": t["p"],
                         "months": t["n"], "fx_vol_ann": pf.ann_vol(fx.loc[start:end]),
                         "months_carry_positive": int((carry.loc[start:end] > 0).sum())})
    raw = pd.DataFrame(rows)
    pretty = raw.assign(carry_ann=raw.carry_ann.map(pct), fx_return_ann=raw.fx_return_ann.map(pct),
                        fx_vol_ann=raw.fx_vol_ann.map(pct),
                        hedge_pnl_ann=[f"{pct(v)}{stars(p)}" for v, p in zip(raw.hedge_pnl_ann, raw.p)],
                        t=raw.t.map("{:.2f}".format), p=raw.p.map("{:.3f}".format))
    last = df.index[-1]
    latest = {c: PPY * df.loc[last, f"fwd_prem_{c}"] for c in ["USD", "EUR"]}
    ratio = {c: latest[c] / (PPY * df[f"fwd_prem_{c}"].mean()) for c in ["USD", "EUR"]}
    rates = {c: df.loc[last, f"rate_{c}"] for c in ["CHF", "USD", "EUR"]}
    note = ("Hedge P&L = carry - FX return (annualised arithmetic means). carry < 0 is the "
            "interest-rate cost of selling the currency forward; fx_return < 0 means the franc "
            "appreciated, which the hedge earns back. t and p test hedge P&L = 0 (Newey-West).\n\n"
            f"Carry used for the last month in the sample ({last:%b %Y}, rates of the previous "
            f"month: CHF {rates['CHF']:.2f}%, USD {rates['USD']:.2f}%, EUR {rates['EUR']:.2f}%): "
            f"USD {pct(latest['USD'], 2)} per year, EUR {pct(latest['EUR'], 2)} per year, "
            f"i.e. {ratio['USD']:.2f} and {ratio['EUR']:.2f} times the full-sample average carry.")
    save_table("t3_cost_of_hedging", "Table 3. What hedging cost or earned, per currency",
               pretty, raw, note=note)
    fx_levels = pd.DataFrame({
        "USDCHF": dp.period_end(load_raw("EURCHF") / load_raw("EURUSD")),
        "EURCHF": dp.period_end(load_raw("EURCHF"))}).loc[config.SAMPLE_START:config.SAMPLE_END]
    plotting.plot_currencies(df, fx_levels)


# ---------------------------------------------------------------------------
# Step 4. Minimum-variance hedge ratio
# ---------------------------------------------------------------------------
def step4_hedge_ratio(streams):
    print("Step 4: minimum-variance hedge ratio")
    rows, curves, static, h_star = [], {}, {}, {}
    grid = np.round(np.arange(0, 2.0001, 0.01), 2)
    for name in ORDER:
        s = streams[name]
        m = hg.min_variance_hedge(s)
        h_star[name] = m["h_star"]
        curves[name] = hg.vol_curve(s, grid)
        static[name] = {h: pf.ann_vol(hg.hedged_return(s, h)) for h in config.HEDGE_RATIOS}
        static[name]["h*"] = pf.ann_vol(hg.hedged_return(s, m["h_star"]))
        rows.append({"asset": NAMES[name], **m, "vol_h0": static[name][0.0],
                     "vol_h1": static[name][1.0], "vol_hstar": static[name]["h*"]})
    raw = pd.DataFrame(rows)
    pretty = pd.DataFrame({
        "asset": raw.asset,
        "h* [95% CI]": [fmt_h(m) for m in rows],
        "p (h*=0)": raw.p_h_eq_0.map("{:.3f}".format),
        "p (h*=1)": raw.p_h_eq_1.map("{:.3f}".format),
        "R² (variance removable)": raw.r2.map(pct),
        "vol h=0": raw.vol_h0.map(pct), "vol h=1": raw.vol_h1.map(pct),
        "vol h*": raw.vol_hstar.map(pct), "months": raw.n})
    save_table("t4a_hedge_ratio", "Table 4a. Minimum-variance hedge ratio, Jan 2000 - Sep 2026",
               pretty, raw,
               note="h* = slope of the unhedged franc return on the currency return net of "
                    "carry. h* < 1: the currency partly hedges the asset by itself; h* > 1: the "
                    "currency adds to the asset's risk, so hedging more than 100% lowers "
                    "volatility further. R² = share of the variance removed by hedging at h*.")
    plotting.plot_vol_curves(curves, h_star, static)

    rows = []
    for start, end, label in config.SUBPERIODS:
        row = {"period": label}
        for name in ORDER:
            m = hg.min_variance_hedge(streams[name], slice(start, end))
            row[NAMES[name]] = fmt_h(m)
            row[f"{name}_raw"] = m["h_star"]
        rows.append(row)
    raw = pd.DataFrame(rows)
    save_table("t4b_hedge_ratio_subperiods", "Table 4b. Minimum-variance hedge ratio by subperiod",
               raw[["period"] + [NAMES[n] for n in ORDER]], raw,
               note="95% confidence intervals in brackets (Newey-West).")

    rolling = {name: hg.rolling_hedge_ratio(streams[name]) for name in ORDER}
    out = pd.concat({name: r["beta"] for name, r in rolling.items()}, axis=1)
    out.to_csv(config.TABLE_DIR / "rolling_hedge_ratio_60m.csv")
    last = out.dropna().index[-1]
    summary = pd.DataFrame([{"asset": NAMES[n], "min": out[n].min(), "min_date": out[n].idxmin(),
                             "max": out[n].max(), "max_date": out[n].idxmax(),
                             "latest": out.loc[last, n]} for n in ORDER])
    pretty = summary.assign(min=summary["min"].map("{:.2f}".format),
                            max=summary["max"].map("{:.2f}".format),
                            latest=summary.latest.map("{:.2f}".format),
                            min_date=summary.min_date.dt.strftime("%Y-%m"),
                            max_date=summary.max_date.dt.strftime("%Y-%m"))
    save_table("t4c_rolling_hedge_ratio",
               f"Table 4c. Rolling 60-month hedge ratio: range and latest value (window ending {last:%b %Y})",
               pretty, summary)
    plotting.plot_rolling_hedge_ratios(rolling)
    return h_star


# ---------------------------------------------------------------------------
# Step 5. Out of sample: could an investor have used h* in real time?
# ---------------------------------------------------------------------------
def step5_out_of_sample(streams):
    print("Step 5: out-of-sample test")
    rows, vols = [], {}
    for name in ORDER:
        s = streams[name]
        oos = hg.out_of_sample_hedge(s)
        idx = oos.index
        strategies = {H_LABEL[h]: hg.hedged_return(s, h).loc[idx] for h in config.HEDGE_RATIOS}
        strategies["rolling h* (0 to 1)"] = oos["R"]
        vols[name] = {}
        for label, r in strategies.items():
            stats = pf.summary(r, s["rf"].loc[idx])
            rows.append({"asset": NAMES[name], "strategy": label, **stats,
                         "avg_h": oos["h_used"].mean() if label.startswith("rolling") else np.nan})
        for h in config.HEDGE_RATIOS:
            vols[name][h] = pf.ann_vol(strategies[H_LABEL[h]])
        vols[name]["h*"] = pf.ann_vol(oos["R"])
    raw = pd.DataFrame(rows)
    pretty = raw.assign(cagr=raw.cagr.map(pct), vol=raw.vol.map(pct),
                        sharpe=raw.sharpe.map("{:.2f}".format), max_dd=raw.max_dd.map(pct),
                        avg_h=raw.avg_h.map(lambda v: "" if pd.isna(v) else f"{v:.2f}"))
    pretty = pretty.drop(columns=["worst", "worst_date"])
    start, end = idx.min(), idx.max()
    save_table("t5_out_of_sample",
               f"Table 5. Out of sample, {start:%b %Y} - {end:%b %Y}: static rules vs rolling h*",
               pretty, raw,
               note="Each month the rolling rule uses the h* estimated on the previous 60 months "
                    "only, capped between 0 and 1. avg_h = average hedge ratio it used.")
    plotting.plot_out_of_sample(pd.DataFrame(vols).T.loc[ORDER], start, end)


# ---------------------------------------------------------------------------
# Step 6. Stress months
# ---------------------------------------------------------------------------
def step6_stress(df, streams):
    print("Step 6: stress months")
    port = streams["PORT"]
    local = port["r_local"]
    rows = []
    for d in local.nsmallest(10).index:
        rows.append({"month": d.strftime("%Y-%m"), "portfolio_local": local[d],
                     "USD_vs_CHF": df.loc[d, "r_fx_USD"], "EUR_vs_CHF": df.loc[d, "r_fx_EUR"],
                     **{H_LABEL[h]: hg.hedged_return(port, h)[d] for h in config.HEDGE_RATIOS}})
    raw = pd.DataFrame(rows)
    save_table("t6a_worst_months",
               "Table 6a. The 10 worst months of the foreign portfolio in local currency",
               raw.assign(**{c: raw[c].map(pct) for c in raw.columns if c != "month"}), raw,
               note="Columns h = 0 / 0.5 / 1 are the portfolio return in francs.")

    stress = local <= local.quantile(0.10)
    rows = []
    for ccy in ["USD", "EUR"]:
        data = pd.DataFrame({"y": df[f"r_fx_{ccy}"], "stress": stress.astype(float)})
        res = ols_nw(data, "y", ["stress"])
        rows.append({"currency": ccy, "months_stress": int(stress.sum()),
                     "fx_normal": res.params["const"],
                     "fx_stress": res.params["const"] + res.params["stress"],
                     "difference": res.params["stress"], "t": res.tvalues["stress"],
                     "p": res.pvalues["stress"]})
    raw = pd.DataFrame(rows)
    save_table("t6b_currency_in_stress",
               "Table 6b. Average monthly currency return vs the franc: stress months vs the rest",
               raw.assign(fx_normal=raw.fx_normal.map(lambda v: pct(v, 2)),
                          fx_stress=raw.fx_stress.map(lambda v: pct(v, 2)),
                          difference=[f"{pct(v, 2)}{stars(p)}" for v, p in zip(raw.difference, raw.p)],
                          t=raw.t.map("{:.2f}".format), p=raw.p.map("{:.3f}".format)),
               raw,
               note="Stress months = worst 10% of months for the foreign portfolio in local "
                    f"currency (return <= {pct(local.quantile(0.10))}). Negative = the currency "
                    "fell against the franc, which hurts an unhedged Swiss investor.")

    avg = pd.DataFrame({h: {name: hg.hedged_return(streams[name], h)[stress].mean() for name in ORDER}
                        for h in config.HEDGE_RATIOS})
    raw = avg.reset_index(names="asset_key")
    raw.insert(0, "asset", raw.asset_key.map(NAMES))
    save_table("t6c_stress_by_asset",
               "Table 6c. Average monthly return in francs during the stress months",
               raw.drop(columns="asset_key").rename(columns=H_LABEL)
                  .assign(**{H_LABEL[h]: raw[h].map(pct) for h in config.HEDGE_RATIOS}),
               raw.rename(columns=H_LABEL))
    plotting.plot_stress(avg.loc[ORDER])

    rows = []
    for ccy in ["USD", "EUR"]:
        for d in df[f"r_fx_{ccy}"].nsmallest(5).index:
            rows.append({"currency": ccy, "month": d.strftime("%Y-%m"),
                         "currency_vs_CHF": df.loc[d, f"r_fx_{ccy}"],
                         **{f"portfolio {H_LABEL[h]}": hg.hedged_return(port, h)[d]
                            for h in config.HEDGE_RATIOS}})
    raw = pd.DataFrame(rows)
    save_table("t6d_worst_currency_months",
               "Table 6d. The 5 worst months of each currency against the franc",
               raw.assign(**{c: raw[c].map(pct) for c in raw.columns if c not in ("currency", "month")}),
               raw)


# ---------------------------------------------------------------------------
# Step 7. Robustness
# ---------------------------------------------------------------------------
def step7_robustness(df, streams):
    print("Step 7: robustness")
    variants = {
        "Baseline (monthly, ECB cross)": (hg.asset_streams(df), None, PPY),
        "USD/CHF from Fed H.10": (hg.asset_streams(dp.build_returns("M", "fed")), None, PPY),
        "Quarterly returns and hedges": (hg.asset_streams(dp.build_returns("Q")), None, 4),
        "Without the SNB floor months": (streams, ~df["floor_period"], PPY),
    }
    rows = []
    for label, (st, mask, ppy) in variants.items():
        for name in ORDER:
            s = st[name] if mask is None else st[name][mask]
            m = hg.min_variance_hedge(s)
            v0 = pf.ann_vol(hg.hedged_return(s, 0.0), ppy)
            v1 = pf.ann_vol(hg.hedged_return(s, 1.0), ppy)
            t = mean_test(s["H"])
            rows.append({"variant": label, "asset": NAMES[name], "h_star": m["h_star"],
                         "ci": fmt_h(m), "p_h_eq_1": m["p_h_eq_1"], "r2": m["r2"],
                         "vol_h0": v0, "vol_h1": v1, "hedge_pnl_ann": ppy * t["mean"],
                         "p_hedge_pnl": t["p"], "n": m["n"]})
    raw = pd.DataFrame(rows)
    pretty = pd.DataFrame({
        "variant": raw.variant, "asset": raw.asset, "h* [95% CI]": raw.ci,
        "p (h*=1)": raw.p_h_eq_1.map("{:.3f}".format),
        "vol h=0": raw.vol_h0.map(pct), "vol h=1": raw.vol_h1.map(pct),
        "hedge P&L ann.": [f"{pct(v)}{stars(p)}" for v, p in zip(raw.hedge_pnl_ann, raw.p_hedge_pnl)],
        "periods": raw.n})
    save_table("t7_robustness", "Table 7. Robustness checks", pretty, raw,
               note="Quarterly: quarter-end prices, 3-month hedges rolled every quarter. "
                    f"Without the floor: drops {config.FLOOR_START[:7]} to {config.FLOOR_END[:7]} "
                    "(affects only the euro side, but is applied to all rows for comparability).")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true", help="re-download all data")
    args = parser.parse_args()

    download_all(refresh=args.refresh)
    plotting.setup_style()
    df = dp.build_returns("M")
    config.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(config.PROCESSED_DIR / "monthly_returns.csv")
    streams = hg.asset_streams(df)

    step0_data_checks(df)
    step1_components(df, streams)
    step2_performance(streams)
    step3_cost(df)
    step4_hedge_ratio(streams)
    step5_out_of_sample(streams)
    step6_stress(df, streams)
    step7_robustness(df, streams)
    write_summary()
    print(f"Done. Tables in {config.TABLE_DIR}, figures in {config.FIG_DIR}, "
          f"summary in results/summary.md")


if __name__ == "__main__":
    main()
