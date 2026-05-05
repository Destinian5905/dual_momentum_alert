import unittest
import sys
import types

import pandas as pd

sys.modules.setdefault("yfinance", types.SimpleNamespace(download=lambda *args, **kwargs: None))
sys.modules.setdefault("requests", types.SimpleNamespace(post=lambda *args, **kwargs: None))

import monthly_dual_momentum_alert as app


class ConfigurableMomentumTests(unittest.TestCase):
    def test_load_config_can_disable_asset_and_criterion(self):
        raw = {
            "risk_free_asset": "SPY",
            "top_n": 1,
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
        returns = prices.pct_change()
        rf = pd.Series(0.0, index=dates)

        metric = app.calculate_metric(returns, prices, "mdd_6m", rf)
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


if __name__ == "__main__":
    unittest.main()
