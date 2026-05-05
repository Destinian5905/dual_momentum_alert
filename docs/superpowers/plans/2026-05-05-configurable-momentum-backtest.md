# Configurable Momentum Backtest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make ranking criteria and asset universe configurable, then backtest the selected universe from a long historical start and report the best CAGR, best risk-adjusted, and lowest MDD strategies.

**Architecture:** Keep the existing one-file GitHub Actions entrypoint intact, but move fixed constants into a JSON-backed configuration loader. Reuse one scoring engine for latest alerts and backtests so MDD and future criteria behave consistently. Add focused `unittest` tests around config loading, criterion scoring, and strategy recommendation.

**Tech Stack:** Python 3.12, pandas, numpy, yfinance, requests, openpyxl, unittest.

---

### Task 1: Test Configurable Criteria And Assets

**Files:**
- Create: `tests/test_configurable_momentum.py`
- Modify: `monthly_dual_momentum_alert.py`

- [x] **Step 1: Write failing tests**

```python
import unittest

import pandas as pd

import monthly_dual_momentum_alert as app


class ConfigurableMomentumTests(unittest.TestCase):
    def test_load_config_can_disable_asset_and_criterion(self):
        raw = {
            "assets": [
                {"key": "SPY", "name": "SPY", "ticker": "SPY", "currency": "USD", "enabled": True},
                {"key": "QQQ", "name": "QQQ", "ticker": "QQQ", "currency": "USD", "enabled": False},
            ],
            "criteria": [
                {"id": "return_1m", "weight": 1.0, "enabled": True},
                {"id": "mdd_6m", "weight": 1.0, "enabled": False},
            ],
        }
        config = app.normalize_config(raw)
        self.assertEqual(list(config["assets"].keys()), ["SPY"])
        self.assertEqual([c["id"] for c in config["criteria"]], ["return_1m"])

    def test_mdd_score_rewards_smaller_drawdown(self):
        dates = pd.date_range("2020-01-31", periods=7, freq="ME")
        prices = pd.DataFrame(
            {
                "LOW_DD": [100, 101, 102, 103, 104, 105, 106],
                "HIGH_DD": [100, 120, 80, 85, 90, 95, 100],
            },
            index=dates,
        )
        metric = app.calculate_metric(prices.pct_change(), prices, "mdd_6m", pd.Series(0.0, index=dates))
        scores = app.rank_metric(metric, app.CRITERIA_DEFINITIONS["mdd_6m"])
        self.assertGreater(scores.loc[dates[-1], "LOW_DD"], scores.loc[dates[-1], "HIGH_DD"])

    def test_recommendations_pick_three_named_objectives(self):
        results = [
            {"strategy": "A", "cagr": 0.2, "sharpe": 0.7, "sortino": 1.0, "mdd": -0.4},
            {"strategy": "B", "cagr": 0.1, "sharpe": 1.2, "sortino": 1.5, "mdd": -0.2},
            {"strategy": "C", "cagr": 0.05, "sharpe": 0.5, "sortino": 0.6, "mdd": -0.1},
        ]
        recommendations = app.select_backtest_recommendations(results)
        self.assertEqual(recommendations["highest_cagr"]["strategy"], "A")
        self.assertEqual(recommendations["highest_risk_adjusted"]["strategy"], "B")
        self.assertEqual(recommendations["lowest_mdd"]["strategy"], "C")
```

- [x] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_configurable_momentum -v`

Expected: FAIL because `normalize_config`, `calculate_metric`, `CRITERIA_DEFINITIONS`, and `select_backtest_recommendations` do not exist yet.

### Task 2: Add Configuration Model And Dynamic Criteria

**Files:**
- Modify: `monthly_dual_momentum_alert.py`
- Create: `dual_momentum_config.example.json`

- [x] **Step 1: Implement config loader**

Add `DEFAULT_CONFIG`, `CRITERIA_DEFINITIONS`, `normalize_config`, and `load_config` so assets and criteria can be enabled/disabled by JSON.

- [x] **Step 2: Implement dynamic scoring**

Replace fixed weighted score blocks with `calculate_metric`, `rank_metric`, and `calculate_total_score`, including MDD criteria where lower drawdown ranks higher.

- [x] **Step 3: Add example config**

Create `dual_momentum_config.example.json` with default assets, default weights, and commented-by-name candidate criteria through JSON fields.

- [x] **Step 4: Run tests**

Run: `python -m unittest tests.test_configurable_momentum -v`

Expected: PASS.

### Task 3: Add Backtest Recommendations

**Files:**
- Modify: `monthly_dual_momentum_alert.py`
- Test: `tests/test_configurable_momentum.py`

- [x] **Step 1: Implement monthly backtest**

Add `run_backtest`, `build_strategy_candidates`, `evaluate_strategy_candidates`, and `select_backtest_recommendations`. Use one-month-lagged scores to avoid lookahead bias.

- [x] **Step 2: Include three recommendation objectives**

Return:
- `highest_cagr`: maximum CAGR.
- `highest_risk_adjusted`: maximum average of Sharpe and Sortino.
- `lowest_mdd`: least negative maximum drawdown.

- [x] **Step 3: Add output**

Include current config backtest and three recommendations in Telegram text and Excel workbook.

- [x] **Step 4: Run tests**

Run: `python -m unittest tests.test_configurable_momentum -v`

Expected: PASS.

### Task 4: CLI, Docs, And Verification

**Files:**
- Modify: `monthly_dual_momentum_alert.py`
- Modify: `README.md`

- [x] **Step 1: Add CLI flags**

Add `--config`, `--skip-backtest`, and keep `--force` and `--no-send` unchanged.

- [x] **Step 2: Document usage**

Document how to copy the example config, add Yahoo Finance tickers, disable criteria/assets, and run locally without Telegram.

- [x] **Step 3: Verify compile and tests**

Run:
- `python -m py_compile monthly_dual_momentum_alert.py`
- `python -m unittest tests.test_configurable_momentum -v`

Expected: PASS.

- [x] **Step 4: Commit and push**

Run:
- `git status --short`
- `git add monthly_dual_momentum_alert.py dual_momentum_config.example.json README.md tests/test_configurable_momentum.py docs/superpowers/plans/2026-05-05-configurable-momentum-backtest.md`
- `git commit -m "feat: add configurable momentum backtests"`
- `git push origin main`

Expected: branch `main` pushed to GitHub.
