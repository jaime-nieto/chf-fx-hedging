### Table 5. Out of sample, Jan 2005 - Sep 2026: static rules vs rolling h*

| asset | strategy | cagr | vol | sharpe | max_dd | avg_h |
|---|---|---|---|---|---|---|
| US equities (S&P 500 TR) | h = 0 | 9.4% | 15.2% | 0.65 | -52.1% |  |
| US equities (S&P 500 TR) | h = 0.5 | 9.0% | 14.3% | 0.67 | -51.9% |  |
| US equities (S&P 500 TR) | h = 1 | 8.4% | 14.9% | 0.61 | -52.6% |  |
| US equities (S&P 500 TR) | rolling h* (0 to 1) | 8.8% | 14.4% | 0.64 | -52.7% | 0.62 |
| US Treasuries 10y | h = 0 | 1.1% | 10.8% | 0.14 | -31.7% |  |
| US Treasuries 10y | h = 0.5 | 0.9% | 7.9% | 0.13 | -30.9% |  |
| US Treasuries 10y | h = 1 | 0.5% | 7.3% | 0.08 | -33.4% |  |
| US Treasuries 10y | rolling h* (0 to 1) | 0.7% | 7.1% | 0.11 | -31.2% | 0.80 |
| German equities (DAX) | h = 0 | 6.1% | 19.0% | 0.40 | -57.6% |  |
| German equities (DAX) | h = 0.5 | 6.8% | 18.0% | 0.45 | -55.2% |  |
| German equities (DAX) | h = 1 | 7.5% | 17.4% | 0.49 | -53.2% |  |
| German equities (DAX) | rolling h* (0 to 1) | 7.6% | 17.5% | 0.50 | -53.2% | 0.89 |
| German Bunds 10y | h = 0 | -0.4% | 7.8% | -0.03 | -36.6% |  |
| German Bunds 10y | h = 0.5 | 0.2% | 6.4% | 0.04 | -34.6% |  |
| German Bunds 10y | h = 1 | 0.7% | 6.3% | 0.12 | -33.2% |  |
| German Bunds 10y | rolling h* (0 to 1) | 0.5% | 6.2% | 0.08 | -33.7% | 0.82 |
| Foreign 60/40 portfolio | h = 0 | 5.3% | 10.6% | 0.52 | -33.9% |  |
| Foreign 60/40 portfolio | h = 0.5 | 5.4% | 9.4% | 0.59 | -33.0% |  |
| Foreign 60/40 portfolio | h = 1 | 5.4% | 9.3% | 0.60 | -32.4% |  |
| Foreign 60/40 portfolio | rolling h* (0 to 1) | 5.6% | 9.2% | 0.62 | -32.4% | 0.85 |

Each month the rolling rule uses the h* estimated on the previous 60 months only, capped between 0 and 1. avg_h = average hedge ratio it used.
