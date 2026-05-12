import unittest
import json
from pathlib import Path

import monthly_dual_momentum_alert as app
import telegram_bot


class TelegramBotTests(unittest.TestCase):
    def test_split_message_keeps_chunks_under_limit(self):
        chunks = telegram_bot.split_message("a" * 25, limit=10)

        self.assertEqual(chunks, ["aaaaaaaaaa", "aaaaaaaaaa", "aaaaa"])

    def test_chat_authorization_matches_expected_id(self):
        self.assertTrue(telegram_bot.is_authorized_chat(123, "123"))
        self.assertFalse(telegram_bot.is_authorized_chat(456, "123"))
        self.assertFalse(telegram_bot.is_authorized_chat(None, "123"))

    def test_config_summary_contains_core_settings(self):
        config = app.normalize_config()

        summary = telegram_bot.format_config_summary(config)

        self.assertIn("top_n: 3", summary)
        self.assertIn("risk_free_asset: SGOV", summary)

    def test_build_asset_entry_infers_key_and_currency(self):
        entry = telegram_bot.build_asset_entry("105190.KS", "KOSPI proxy")

        self.assertEqual(entry["key"], "105190_KS")
        self.assertEqual(entry["ticker"], "105190.KS")
        self.assertEqual(entry["currency"], "KRW")
        self.assertTrue(entry["enabled"])

    def test_apply_asset_add_adds_missing_ticker(self):
        raw = {
            "assets": [],
            "criteria": [{"id": "return_1m", "weight": 1.0, "enabled": True}],
            "risk_free_asset": "SGOV",
            "top_n": 1,
        }
        asset = telegram_bot.build_asset_entry("SGOV", "Cash")

        updated = telegram_bot.apply_asset_add(raw, asset)

        self.assertEqual(updated["assets"][0]["ticker"], "SGOV")
        self.assertTrue(updated["assets"][0]["enabled"])

    def test_apply_asset_remove_disables_existing_ticker(self):
        raw = {
            "assets": [
                {"key": "SGOV", "name": "Cash", "ticker": "SGOV", "currency": "USD", "enabled": True}
            ]
        }

        updated = telegram_bot.apply_asset_remove(raw, "SGOV")

        self.assertFalse(updated["assets"][0]["enabled"])

    def test_set_asset_class_enabled_updates_matching_assets(self):
        raw = {
            "assets": [
                {"key": "A", "ticker": "AAA", "asset_class": "EQ", "enabled": False},
                {"key": "B", "ticker": "BBB", "asset_class": "FI", "enabled": True},
            ],
            "risk_free_asset": "B",
            "top_n": 1,
        }
        updated = telegram_bot.set_asset_class_enabled(raw, "EQ", True)
        self.assertTrue(updated["assets"][0]["enabled"])

    def test_write_config_creates_backup(self):
        path = Path("test_dual_momentum_config.json")
        backups = []
        try:
            path.write_text(json.dumps({"assets": []}), encoding="utf-8")

            telegram_bot.write_config_with_backup(path, {"assets": [{"ticker": "SGOV"}]})

            backups = list(Path(".").glob("test_dual_momentum_config.json.bak.*"))
            self.assertTrue(backups)
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(saved["assets"][0]["ticker"], "SGOV")
        finally:
            if path.exists():
                path.unlink()
            for backup in backups:
                backup.unlink()


if __name__ == "__main__":
    unittest.main()
