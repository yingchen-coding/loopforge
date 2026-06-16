# eval example — score predictions against real outcomes

`predictions.csv` is **illustrative sample data** (not real picks). Each row is a prediction; once a
match resolves you fill in `actual` and the betting `result` (W/L/push), then:

```bash
loopforge eval predictions.csv
# predictions: 4  ·  resolved: 3  ·  pending: 1
# accuracy: 67%  (2/3 correct)
# calibration (Brier, lower=better): 0.x
# P&L: +x.xx  ·  staked: 12.00  ·  ROI: +x%
```

## Auto-validate with the latest data

`eval` is the *scoring* half. To make it self-validating, pair it in a loop:

- **act** = a resolver that fetches the latest real outcomes and fills in `actual`/`result`
  (a script hitting a results API, yfinance for stock calls, your chart for medical predictions —
  whatever the domain's ground truth is).
- **verify** = `loopforge eval predictions.csv --min-accuracy 0.5` — the loop fails its own gate if
  its predictions stop beating the bar.
- **schedule** it (`loopforge schedule install`) and the predictions validate themselves on a cadence.

The CSV is domain-agnostic: soccer bets, stock calls, anything with a predicted value and a later
real outcome.
