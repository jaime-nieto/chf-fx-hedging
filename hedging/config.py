"""
Project settings in one place: paths, sample, data series, portfolio weights.
Change things here, not inside the analysis code.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
FIG_DIR = ROOT / "results" / "figures"
TABLE_DIR = ROOT / "results" / "tables"

# ---------------------------------------------------------------------------
# Sample
# ---------------------------------------------------------------------------
DOWNLOAD_START = "1999-01-01"
SAMPLE_START = "2000-01-01"     # first monthly return: January 2000
SAMPLE_END = "2026-09-30"       # last complete month before the data download

# SNB minimum exchange rate of 1.20 francs per euro (6 Sep 2011 - 15 Jan 2015).
# Kept in the main sample (it is what an investor actually lived through);
# excluded in a robustness check.
FLOOR_START = "2011-09-01"      # first month affected
FLOOR_END = "2015-01-31"        # last month affected (includes the removal)

# ---------------------------------------------------------------------------
# Data series: name -> where it comes from
# ---------------------------------------------------------------------------
SERIES = {
    # Exchange rates: ECB reference rates (fixing at 14:15 CET, daily).
    # Both crosses come from the same fixing, so USD/CHF = EUR/CHF / EUR/USD.
    "EURCHF": {"source": "ecb", "code": "EXR/D.CHF.EUR.SP00.A",
               "description": "Francs per euro, ECB reference rate (daily)"},
    "EURUSD": {"source": "ecb", "code": "EXR/D.USD.EUR.SP00.A",
               "description": "Dollars per euro, ECB reference rate (daily)"},
    "USDCHF_FED": {"source": "fred", "code": "DEXSZUS",
                   "description": "Francs per dollar, Fed H.10 noon New York (daily); robustness only"},
    # Equities: total-return indices (dividends reinvested), local currency
    "SPX_TR": {"source": "yahoo", "code": "^SP500TR",
               "description": "S&P 500 Total Return index, USD (daily close)"},
    "SPX": {"source": "yahoo", "code": "^GSPC",
            "description": "S&P 500 price index, USD; data check only (dividend gap)"},
    "DAX": {"source": "yahoo", "code": "^GDAXI",
            "description": "DAX, EUR; a performance index (dividends reinvested) by construction"},
    # Government bond yields, 10-year maturity, % per year
    "UST10Y": {"source": "fred", "code": "DGS10",
               "description": "US Treasury 10-year constant-maturity yield, % (daily)"},
    "BUND10Y": {"source": "bbk", "code": "BBSIS/D.I.ZST.ZI.EUR.S1311.B.A604.R10XX.R.A.A._Z._Z.A",
                "description": "German Federal securities, 10-year yield from the Bundesbank "
                               "term structure (Svensson), % (daily)"},
    # Short-term interest rates (3 months, monthly averages, % per year)
    "RATE_CHF": {"source": "fred", "code": "IR3TIB01CHM156N",
                 "description": "Switzerland 3-month interbank rate, OECD MEI (monthly average)"},
    "RATE_USD": {"source": "fred", "code": "IR3TIB01USM156N",
                 "description": "United States 3-month interbank rate, OECD MEI (monthly average)"},
    "RATE_EUR": {"source": "ecb", "code": "FM/M.U2.EUR.RT.MM.EURIBOR3MD_.HSTA",
                 "description": "Euribor 3-month, ECB (monthly average)"},
    # Bond ETFs (prices adjusted for distributions): only used to validate the
    # bond returns we build from yields
    "ETF_UST": {"source": "yahoo_adj", "code": "IEF",
                "description": "iShares 7-10 Year Treasury Bond ETF, adjusted close; data check only"},
    "ETF_BUND": {"source": "yahoo_adj", "code": "EXHD.DE",
                 "description": "iShares eb.rexx Government Germany 5.5-10.5yr ETF, adjusted close; "
                                "data check only"},
}

# ---------------------------------------------------------------------------
# Assets, currencies and the example portfolio
# ---------------------------------------------------------------------------
# Each foreign asset: its local-currency return series and its currency
ASSETS = {
    "US_EQ": {"label": "US equities (S&P 500 TR)", "currency": "USD"},
    "US_BD": {"label": "US Treasuries 10y", "currency": "USD"},
    "DE_EQ": {"label": "German equities (DAX)", "currency": "EUR"},
    "DE_BD": {"label": "German Bunds 10y", "currency": "EUR"},
}
# A simple 60/40 foreign portfolio, rebalanced every month
PORTFOLIO = {"US_EQ": 0.30, "DE_EQ": 0.30, "US_BD": 0.20, "DE_BD": 0.20}

BOND_MATURITY = 10              # years; bonds are rebuilt every month at par
HEDGE_RATIOS = (0.0, 0.5, 1.0)  # the three static rules compared everywhere
ROLLING_MONTHS = 60             # window for the rolling hedge ratio (5 years)
PERIODS_PER_YEAR = 12

SUBPERIODS = [
    ("2000-01-01", "2007-12-31", "2000-07: positive rates"),
    ("2008-01-01", "2014-12-31", "2008-14: crisis and SNB floor"),
    ("2015-01-01", "2021-12-31", "2015-21: negative CHF rates"),
    ("2022-01-01", "2026-09-30", "2022-26: rate hikes and after"),
]
