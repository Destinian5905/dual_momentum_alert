# Telegram VPS Bot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a long-running Telegram command bot for Oracle VPS deployment while preserving the existing GitHub Actions alert script.

**Architecture:** Keep `monthly_dual_momentum_alert.py` as the computation and batch alert module, and add `telegram_bot.py` as the VPS polling entrypoint. The bot validates `TELEGRAM_CHAT_ID`, calls shared report generation code, splits long Telegram replies, and ships with systemd/env deployment examples.

**Tech Stack:** Python 3.12, python-telegram-bot, pandas, numpy, yfinance, requests, openpyxl, unittest, systemd.

---

### Task 1: Shared Report Generation

**Files:**
- Modify: `monthly_dual_momentum_alert.py`
- Test: `tests/test_configurable_momentum.py`

- [ ] **Step 1: Add failing test for reusable report generation**

```python
def test_generate_report_can_skip_excel_save(self):
    config = app.normalize_config({
        "risk_free_asset": "SGOV",
        "top_n": 1,
        "assets": [
            {"key": "SGOV", "name": "Cash", "ticker": "SGOV", "currency": "USD", "enabled": True},
        ],
        "criteria": [{"id": "return_1m", "weight": 1.0, "enabled": True}],
    })
    prices = pd.DataFrame({"SGOV": [100, 101, 102]}, index=pd.date_range("2024-01-31", periods=3, freq="ME"))
    result = app.generate_report_from_prices(prices, config, include_backtest=False, save_excel=False)
    self.assertIn("Dual Momentum Monthly Signal", result["message"])
    self.assertIsNone(result["output_file"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_configurable_momentum -v`

Expected: FAIL because `generate_report_from_prices` does not exist.

- [ ] **Step 3: Implement shared helpers**

Add:

```python
def generate_report_from_prices(prices_krw, config, include_backtest=True, save_excel=True):
    signal = calc_latest_signal(prices_krw, config)
    backtest_results = []
    if include_backtest and config.get("backtest", {}).get("enabled", True):
        backtest_results = evaluate_strategy_candidates(prices_krw, config)
    output_file = save_output(signal, backtest_results) if save_excel else None
    message = build_message(signal, backtest_results)
    return {"message": message, "output_file": output_file, "signal": signal, "backtest_results": backtest_results}
```

and:

```python
def generate_report(config_path=None, include_backtest=True, save_excel=True):
    config = load_config(config_path)
    prices_krw, _ = build_monthly_prices_krw(config)
    return generate_report_from_prices(prices_krw, config, include_backtest=include_backtest, save_excel=save_excel)
```

- [ ] **Step 4: Update `main` to use `generate_report`**

Use `include_backtest=not args.skip_backtest`, print `result["message"]`, and send Telegram only from the batch script when `--no-send` is not set.

- [ ] **Step 5: Run tests**

Run: `python -m unittest tests.test_configurable_momentum -v`

Expected: PASS.

### Task 2: Telegram Bot Entry Point

**Files:**
- Create: `telegram_bot.py`
- Create: `tests/test_telegram_bot.py`
- Modify: `requirements.txt`

- [ ] **Step 1: Write failing bot tests**

```python
def test_split_message_keeps_chunks_under_limit(self):
    chunks = telegram_bot.split_message("a" * 25, limit=10)
    self.assertEqual(chunks, ["aaaaaaaaaa", "aaaaaaaaaa", "aaaaa"])

def test_chat_authorization_matches_expected_id(self):
    self.assertTrue(telegram_bot.is_authorized_chat(123, "123"))
    self.assertFalse(telegram_bot.is_authorized_chat(456, "123"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_telegram_bot -v`

Expected: FAIL because `telegram_bot.py` does not exist.

- [ ] **Step 3: Implement pure bot helpers**

Add `split_message`, `is_authorized_chat`, `format_config_summary`, `format_assets`, and `format_criteria`.

- [ ] **Step 4: Implement async command handlers**

Use `python-telegram-bot` `Application` and `CommandHandler` for `/start`, `/help`, `/signal`, `/backtest`, `/config`, `/assets`, and `/criteria`. Use `asyncio.to_thread` for signal and backtest calculation.

- [ ] **Step 5: Add dependency**

Append `python-telegram-bot` to `requirements.txt`.

- [ ] **Step 6: Run tests**

Run: `python -m unittest tests.test_configurable_momentum tests.test_telegram_bot -v`

Expected: PASS.

### Task 3: VPS Deployment Files And Docs

**Files:**
- Create: `.env.example`
- Create: `deploy/dual-momentum-bot.service`
- Modify: `README.md`

- [ ] **Step 1: Add env example**

Create:

```env
TELEGRAM_BOT_TOKEN=123456:replace-me
TELEGRAM_CHAT_ID=123456789
DUAL_MOMENTUM_CONFIG=/opt/dual_momentum_alert/dual_momentum_config.json
```

- [ ] **Step 2: Add systemd service**

Create service that runs `/opt/dual_momentum_alert/.venv/bin/python /opt/dual_momentum_alert/telegram_bot.py` from `/opt/dual_momentum_alert`, loads `/etc/dual-momentum-alert.env`, restarts on failure, and runs as user `ubuntu`.

- [ ] **Step 3: Document Oracle VPS installation**

Add commands for `git clone`, venv setup, `pip install -r requirements.txt`, env file creation, service installation, logs, restart, and updates.

- [ ] **Step 4: Verify**

Run:
- `python -m py_compile monthly_dual_momentum_alert.py telegram_bot.py`
- `python -m unittest tests.test_configurable_momentum tests.test_telegram_bot -v`

Expected: PASS.

### Task 4: Commit And Push

**Files:**
- All changed files

- [ ] **Step 1: Stage files**

Run:

```bash
git add monthly_dual_momentum_alert.py telegram_bot.py requirements.txt README.md .env.example deploy/dual-momentum-bot.service tests/test_configurable_momentum.py tests/test_telegram_bot.py docs/superpowers/specs/2026-05-05-telegram-vps-bot-design.md docs/superpowers/plans/2026-05-05-telegram-vps-bot.md
```

- [ ] **Step 2: Commit**

Run:

```bash
git commit -m "feat: add telegram command bot"
```

- [ ] **Step 3: Push**

Run:

```bash
git push origin main
```

Expected: `main -> main`.
