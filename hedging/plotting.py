"""
All charts. Colour always means the same thing in every figure:

    orange = unhedged (h = 0)      aqua = half hedged (h = 0.5)
    blue   = fully hedged (h = 1)  violet = minimum-variance hedge ratio h*

Single-series context lines (exchange rates, carry) are drawn in dark grey.
No chart uses two y-axes: different units go in separate panels.
"""
import textwrap

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import matplotlib.ticker
import numpy as np
import pandas as pd

from . import config

STRATEGY_COLORS = {0.0: "#eb6834", 0.5: "#1baf7a", 1.0: "#2a78d6", "h*": "#4a3aa7"}
STRATEGY_LABELS = {0.0: "Unhedged (h = 0)", 0.5: "Half hedged (h = 0.5)",
                   1.0: "Fully hedged (h = 1)", "h*": "Rolling minimum-variance h*"}
INK, INK_2, INK_3 = "#0b0b0b", "#52514e", "#8a8985"
SURFACE, GRID, SHADE = "#fcfcfb", "#e4e3df", "#ebeae6"
CONTEXT = "#3d3d3a"

NAMES = {**{k: v["label"] for k, v in config.ASSETS.items()},
         "PORT": "Foreign 60/40 portfolio"}
ORDER = ["US_EQ", "US_BD", "DE_EQ", "DE_BD", "PORT"]


def setup_style():
    plt.rcParams.update({
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
        "font.size": 9.5, "text.color": INK, "axes.labelcolor": INK_2,
        "axes.titlesize": 10.5, "axes.titlelocation": "left", "axes.titlecolor": INK,
        "xtick.color": INK_2, "ytick.color": INK_2, "axes.edgecolor": INK_3,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "axes.grid.axis": "y", "grid.color": GRID, "grid.linewidth": 0.8,
        "legend.frameon": False, "legend.fontsize": 9, "lines.linewidth": 1.6,
    })


def _save(fig, name):
    config.FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(config.FIG_DIR / name, dpi=150, bbox_inches="tight")
    plt.close(fig)


def _shade_floor(ax, label=False):
    ax.axvspan(pd.Timestamp(config.FLOOR_START), pd.Timestamp(config.FLOOR_END),
               color=SHADE, zorder=0, lw=0, label="SNB floor (EUR/CHF ≥ 1.20)" if label else None)


def _date_axis(ax):
    locator = mdates.AutoDateLocator(maxticks=7)
    ax.xaxis.set_major_locator(locator)
    ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))


def _end_labels(ax, items, min_gap=0.05):
    """
    Write value labels at the right end of lines without overlaps.
    items: list of (y_value, text). Call after the axis limits are final.
    """
    to_axes = ax.transData + ax.transAxes.inverted()
    x_end = ax.get_xlim()[1]
    pos = sorted((to_axes.transform((x_end, y))[1], text) for y, text in items)
    for i in range(1, len(pos)):                       # push labels apart upwards
        if pos[i][0] - pos[i - 1][0] < min_gap:
            pos[i] = (pos[i - 1][0] + min_gap, pos[i][1])
    for y, text in pos:
        ax.text(1.005, y, text, transform=ax.transAxes, fontsize=8, color=INK, va="center")


def _log_ticks(ax):
    """Readable ticks on a log axis (0.5, 1, 2, 3, ...)."""
    lo, hi = ax.get_ylim()
    candidates = [0.25, 0.5, 0.75, 1, 1.5, 2, 3, 4, 5, 6, 8, 10]
    ax.yaxis.set_major_locator(matplotlib.ticker.FixedLocator(
        [t for t in candidates if lo <= t <= hi]))
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:g}"))
    ax.yaxis.set_minor_locator(matplotlib.ticker.NullLocator())


def _panel_grid(n=5):
    """Five panels: the four assets in a 2x2 block, the portfolio below."""
    fig = plt.figure(figsize=(10, 10.5))
    gs = fig.add_gridspec(3, 2, hspace=0.42, wspace=0.18)
    axes = [fig.add_subplot(gs[0, 0]), fig.add_subplot(gs[0, 1]),
            fig.add_subplot(gs[1, 0]), fig.add_subplot(gs[1, 1]),
            fig.add_subplot(gs[2, :])]
    return fig, axes[:n]


# ---------------------------------------------------------------------------
def plot_currencies(df, fx_levels):
    """FX level, carry (cost of hedging) and cumulative hedge P&L, per currency."""
    fig, axes = plt.subplots(3, 2, figsize=(10, 8.6), sharex=True)
    for j, ccy in enumerate(["USD", "EUR"]):
        lvl = fx_levels[f"{ccy}CHF"]
        ax = axes[0, j]
        if ccy == "EUR":
            _shade_floor(ax, label=True)
            ax.legend(loc="upper right")
        ax.plot(lvl.index, lvl, color=CONTEXT)
        ax.set_title(f"{ccy}/CHF: francs per {'dollar' if ccy == 'USD' else 'euro'}")

        ax = axes[1, j]
        carry = 100 * config.PERIODS_PER_YEAR * df[f"fwd_prem_{ccy}"]
        ax.axhline(0, color=INK_3, lw=0.8)
        ax.plot(carry.index, carry, color=CONTEXT)
        ax.set_title(f"Carry of the {ccy} hedge, % per year\n(negative = hedging costs money)")

        ax = axes[2, j]
        total = 100 * (df[f"fwd_prem_{ccy}"] - df[f"r_fx_{ccy}"]).cumsum()
        carry_only = 100 * df[f"fwd_prem_{ccy}"].cumsum()
        ax.axhline(0, color=INK_3, lw=0.8)
        ax.plot(total.index, total, color=CONTEXT, label="Hedge P&L (carry + FX)")
        ax.plot(carry_only.index, carry_only, color=INK_3, ls="--", label="Carry only")
        _end_labels(ax, [(total.iloc[-1], f"{total.iloc[-1]:.0f}"),
                         (carry_only.iloc[-1], f"{carry_only.iloc[-1]:.0f}")])
        ax.set_title(f"Cumulative P&L of hedging the {ccy}\n(sum of monthly P&L, % of hedged value)")
        ax.legend(loc="lower left")
        for a in axes[:, j]:
            _date_axis(a)
    fig.suptitle("The two currencies and what it cost (or paid) to hedge them, 2000–2026",
                 x=0.06, ha="left", fontsize=12)
    fig.tight_layout()
    _save(fig, "fig01_currencies.png")


def plot_wealth(streams, hedged_return):
    fig, axes = _panel_grid()
    for ax, name in zip(axes, ORDER):
        s = streams[name]
        if name in ("DE_EQ", "DE_BD", "PORT"):
            _shade_floor(ax, label=(name == "PORT"))
        ends = []
        for h in config.HEDGE_RATIOS:
            w = (1 + hedged_return(s, h)).cumprod()
            ax.plot(w.index, w, color=STRATEGY_COLORS[h], label=STRATEGY_LABELS[h])
            ends.append((w.iloc[-1], f"{w.iloc[-1]:.2f}"))
        ax.set_yscale("log")
        _log_ticks(ax)
        _end_labels(ax, ends)
        ax.set_title(NAMES[name])
        _date_axis(ax)
    axes[-1].legend(loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=4)
    fig.suptitle("Value in francs of 1 CHF invested in January 2000 (log scale)",
                 x=0.06, ha="left", y=0.94, fontsize=12)
    _save(fig, "fig02_wealth.png")


def plot_vol_curves(curves, h_star, static):
    """Annualised volatility as a function of the hedge ratio."""
    fig, axes = _panel_grid()
    for ax, name in zip(axes, ORDER):
        c = 100 * curves[name]
        ax.plot(c.index, c, color=CONTEXT, lw=1.4)
        for h in config.HEDGE_RATIOS:
            v = 100 * static[name][h]
            ax.plot([h], [v], "o", ms=8, color=STRATEGY_COLORS[h], mec=SURFACE, mew=1.5,
                    label=STRATEGY_LABELS[h], zorder=3)
        hs, vs = h_star[name], 100 * static[name]["h*"]
        ax.plot([hs], [vs], "D", ms=8, color=STRATEGY_COLORS["h*"], mec=SURFACE, mew=1.5,
                label="Minimum-variance h* (full sample)", zorder=4)
        ax.annotate(f"h* = {hs:.2f}\nvol {vs:.1f}%", (hs, vs), xytext=(0, 12),
                    textcoords="offset points", ha="center", fontsize=8.5, color=INK)
        ax.set_title(NAMES[name])
        ax.set_xlabel("Hedge ratio h")
        ax.set_ylabel("Volatility, % per year")
        ax.grid(axis="x", color=GRID, lw=0.8)
    axes[-1].legend(loc="upper center", bbox_to_anchor=(0.5, -0.22), ncol=4, fontsize=8.5)
    fig.suptitle("How volatility in francs changes with the hedge ratio (monthly data, 2000–2026)",
                 x=0.06, ha="left", y=0.94, fontsize=12)
    _save(fig, "fig03_vol_vs_hedge_ratio.png")


def plot_rolling_hedge_ratios(rolling):
    fig, axes = _panel_grid()
    for ax, name in zip(axes, ORDER):
        r = rolling[name].dropna()
        if name in ("DE_EQ", "DE_BD", "PORT"):
            _shade_floor(ax, label=(name == "PORT"))
        ax.axhline(1, color=STRATEGY_COLORS[1.0], lw=1, ls="--", label="Full hedge (h = 1)")
        ax.axhline(0, color=STRATEGY_COLORS[0.0], lw=1, ls="--", label="No hedge (h = 0)")
        ax.fill_between(r.index, r["beta"] - 1.96 * r["se"], r["beta"] + 1.96 * r["se"],
                        color=STRATEGY_COLORS["h*"], alpha=0.15, lw=0, label="±1.96 s.e.")
        ax.plot(r.index, r["beta"], color=STRATEGY_COLORS["h*"], label="h*, 60-month window")
        _end_labels(ax, [(r["beta"].iloc[-1], f"{r['beta'].iloc[-1]:.2f}")])
        ax.set_title(NAMES[name])
        _date_axis(ax)
    axes[-1].legend(loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=5, fontsize=8.5)
    fig.suptitle("Minimum-variance hedge ratio over rolling 5-year windows "
                 "(date = end of the window)", x=0.06, ha="left", y=0.94, fontsize=12)
    _save(fig, "fig04_rolling_hedge_ratio.png")


def _grouped_bars(ax, table, keys, value_fmt="{:.1f}"):
    """table: rows = groups (assets), columns = keys (strategies)."""
    n = len(keys)
    width = 0.8 / n
    x = np.arange(len(table))
    for i, k in enumerate(keys):
        vals = table[k].values
        bars = ax.bar(x + (i - (n - 1) / 2) * width, vals, width * 0.92,
                      color=STRATEGY_COLORS[k], label=STRATEGY_LABELS[k], zorder=2)
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, v, value_fmt.format(v), ha="center",
                    va="bottom" if v >= 0 else "top", fontsize=7.5, color=INK)
    ax.set_xticks(x, [textwrap.fill(NAMES[i], 16) for i in table.index])
    ax.axhline(0, color=INK_3, lw=0.8)


def plot_stress(avg_in_stress):
    fig, ax = plt.subplots(figsize=(10, 4.6))
    _grouped_bars(ax, 100 * avg_in_stress, list(config.HEDGE_RATIOS), "{:.1f}")
    ax.set_ylabel("Average monthly return, %")
    ax.set_title("Average return in francs in the worst 10% of months for the portfolio\n"
                 "(stress months chosen by the portfolio's return in local currency)")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=3)
    _save(fig, "fig05_stress_months.png")


def plot_out_of_sample(vols, start, end):
    fig, ax = plt.subplots(figsize=(10, 4.6))
    _grouped_bars(ax, 100 * vols, list(config.HEDGE_RATIOS) + ["h*"], "{:.1f}")
    ax.set_ylabel("Volatility, % per year")
    ax.set_title(f"Out-of-sample volatility, {start:%b %Y}–{end:%b %Y}\n"
                 "Static rules vs a hedge ratio estimated each month on the previous 60 months "
                 "(kept between 0 and 1)")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=4)
    _save(fig, "fig06_out_of_sample.png")
