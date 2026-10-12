"""
Download every series listed in config.SERIES and cache it in data/raw/.

Each series is saved as a two-column CSV (date, value). A manifest.json file
records, for every series, where it came from and when it was downloaded.
Once the cache exists the project runs fully offline.
"""
import io
import json
from datetime import datetime, timezone

import pandas as pd
import requests
import truststore

from . import config

# Use the operating system's certificate store for HTTPS (more robust on
# corporate networks and Windows machines than Python's default bundle).
truststore.inject_into_ssl()

FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={code}"
ECB_URL = "https://data-api.ecb.europa.eu/service/data/{code}?format=csvdata"
BBK_URL = "https://api.statistiken.bundesbank.de/rest/download/{code}?format=csv&lang=en"
YAHOO_URL = "https://finance.yahoo.com/quote/{code}"   # documentation only

MANIFEST = config.RAW_DIR / "manifest.json"


def _get(url):
    # Note: FRED rejects requests that send a fake browser User-Agent, so we
    # keep the default one from the `requests` library.
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    response.encoding = "utf-8-sig"          # the Bundesbank file starts with a BOM
    return response.text


def _yahoo(code, column):
    import yfinance as yf
    df = yf.download(code, start=config.DOWNLOAD_START, auto_adjust=False,
                     progress=False, multi_level_index=False)
    return df[column]


def fetch_yahoo(code):
    return _yahoo(code, "Close")


def fetch_yahoo_adj(code):
    # "Adj Close" adds back dividends/distributions: used for the bond ETFs
    return _yahoo(code, "Adj Close")


def fetch_fred(code):
    df = pd.read_csv(io.StringIO(_get(FRED_URL.format(code=code))))
    return pd.Series(pd.to_numeric(df[code], errors="coerce").values,
                     index=pd.to_datetime(df["observation_date"]))


def fetch_ecb(code):
    df = pd.read_csv(io.StringIO(_get(ECB_URL.format(code=code))))
    return pd.Series(df["OBS_VALUE"].astype(float).values,
                     index=pd.to_datetime(df["TIME_PERIOD"]))


def fetch_bbk(code):
    # The Bundesbank CSV has a few metadata lines on top; data lines start with
    # a date, and missing days are written as "."
    df = pd.read_csv(io.StringIO(_get(BBK_URL.format(code=code))), header=None,
                     usecols=[0, 1], names=["date", "value"], dtype=str)
    df = df[df["date"].str.match(r"^\d{4}-\d{2}-\d{2}$", na=False)]
    return pd.Series(pd.to_numeric(df["value"], errors="coerce").values,
                     index=pd.to_datetime(df["date"]))


FETCHERS = {"yahoo": fetch_yahoo, "yahoo_adj": fetch_yahoo_adj, "fred": fetch_fred,
            "ecb": fetch_ecb, "bbk": fetch_bbk}
URLS = {"yahoo": YAHOO_URL, "yahoo_adj": YAHOO_URL, "fred": FRED_URL,
        "ecb": ECB_URL, "bbk": BBK_URL}


def download_all(refresh=False):
    """Download missing series (or all of them if refresh=True)."""
    config.RAW_DIR.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}

    for name, spec in config.SERIES.items():
        path = config.RAW_DIR / f"{name}.csv"
        if path.exists() and not refresh:
            continue
        print(f"  downloading {name:<11} from {spec['source']} ({spec['code']})")
        series = FETCHERS[spec["source"]](spec["code"]).dropna().sort_index()
        series.index.name = "date"
        series.name = "value"
        series.to_csv(path)

        manifest[name] = {
            "source": spec["source"],
            "code": spec["code"],
            "url": URLS[spec["source"]].format(code=spec["code"]),
            "description": spec["description"],
            "downloaded_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
            "first_date": str(series.index.min().date()),
            "last_date": str(series.index.max().date()),
            "n_obs": int(len(series)),
        }
        MANIFEST.write_text(json.dumps(manifest, indent=2))


def load_raw(name):
    """Read one cached series as a pandas Series indexed by date."""
    path = config.RAW_DIR / f"{name}.csv"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found. Run `python run_all.py` with internet access.")
    df = pd.read_csv(path, parse_dates=["date"], index_col="date")
    return df["value"].rename(name)


if __name__ == "__main__":
    download_all(refresh=False)
