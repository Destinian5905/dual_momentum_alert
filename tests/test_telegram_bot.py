import unittest

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


if __name__ == "__main__":
    unittest.main()
