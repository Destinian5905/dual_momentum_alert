# Telegram Asset Toggle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the authorized Telegram user add or remove Yahoo Finance tickers from the active asset universe through a confirmation flow.

**Architecture:** Add pure config mutation helpers to `telegram_bot.py` so tests can verify add/remove behavior without Telegram network calls. The `/asset TICKER` command checks the current config, asks for confirmation through inline buttons, and only writes `dual_momentum_config.json` after the user confirms. Before writing, the bot creates a timestamped `.bak` copy of the config.

**Tech Stack:** Python 3.12, python-telegram-bot inline keyboards, JSON config files, unittest.

---

### Task 1: Asset Config Helpers

**Files:**
- Modify: `telegram_bot.py`
- Modify: `tests/test_telegram_bot.py`

- [x] **Step 1: Write failing tests**

```python
def test_build_asset_entry_infers_key_and_currency(self):
    entry = telegram_bot.build_asset_entry("105190.KS", "KOSPI proxy")
    self.assertEqual(entry["key"], "105190_KS")
    self.assertEqual(entry["ticker"], "105190.KS")
    self.assertEqual(entry["currency"], "KRW")
    self.assertTrue(entry["enabled"])

def test_toggle_asset_adds_missing_ticker(self):
    raw = {"assets": [], "criteria": [{"id": "return_1m", "weight": 1.0, "enabled": True}], "risk_free_asset": "SGOV", "top_n": 1}
    asset = telegram_bot.build_asset_entry("SGOV", "Cash")
    updated = telegram_bot.apply_asset_add(raw, asset)
    self.assertEqual(updated["assets"][0]["ticker"], "SGOV")

def test_toggle_asset_disables_existing_ticker(self):
    raw = {"assets": [{"key": "SGOV", "name": "Cash", "ticker": "SGOV", "currency": "USD", "enabled": True}]}
    updated = telegram_bot.apply_asset_remove(raw, "SGOV")
    self.assertFalse(updated["assets"][0]["enabled"])
```

- [x] **Step 2: Run tests to verify failure**

Run: `python -m unittest tests.test_telegram_bot -v`

Expected: FAIL because helper functions do not exist.

- [x] **Step 3: Implement helpers**

Add `normalize_ticker`, `asset_key_from_ticker`, `infer_currency`, `build_asset_entry`, `find_asset_by_ticker`, `apply_asset_add`, and `apply_asset_remove`.

- [x] **Step 4: Run tests**

Run: `python -m unittest tests.test_telegram_bot -v`

Expected: PASS.

### Task 2: Persistent Config Writes

**Files:**
- Modify: `telegram_bot.py`
- Modify: `tests/test_telegram_bot.py`

- [x] **Step 1: Write failing tests**

```python
def test_write_config_creates_backup(self):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "dual_momentum_config.json"
        path.write_text(json.dumps({"assets": []}), encoding="utf-8")
        telegram_bot.write_config_with_backup(path, {"assets": [{"ticker": "SGOV"}]})
        self.assertTrue(list(Path(tmp).glob("dual_momentum_config.json.bak.*")))
```

- [x] **Step 2: Implement config path and write helpers**

Add `editable_config_path`, `read_raw_config`, and `write_config_with_backup`. Refuse mutation unless the bot has a real config file path through `DUAL_MOMENTUM_CONFIG` or `dual_momentum_config.json`.

- [x] **Step 3: Run tests**

Run: `python -m unittest tests.test_telegram_bot -v`

Expected: PASS.

### Task 3: Telegram Confirmation Flow

**Files:**
- Modify: `telegram_bot.py`
- Modify: `README.md`

- [x] **Step 1: Add `/asset` command**

If ticker exists and is enabled, send an inline keyboard asking for removal confirmation. If missing or disabled, verify Yahoo Finance has monthly data, then ask for add confirmation.

- [x] **Step 2: Add callback query handler**

Handle callback data for `asset:add:TICKER` and `asset:remove:TICKER`. Re-check authorization and current config before writing.

- [x] **Step 3: Update help and README**

Add `/asset TICKER` to command help and document the confirmation behavior.

- [x] **Step 4: Verify**

Run:
- `python -m py_compile telegram_bot.py monthly_dual_momentum_alert.py`
- `python -m unittest tests.test_configurable_momentum tests.test_telegram_bot -v`

Expected: PASS.

### Task 4: Commit And Push

**Files:**
- All changed files

- [x] **Step 1: Stage files**

Run:

```bash
git add telegram_bot.py README.md tests/test_telegram_bot.py docs/superpowers/plans/2026-05-05-telegram-asset-toggle.md
```

- [x] **Step 2: Commit**

Run:

```bash
git commit -m "feat: add telegram asset toggle command"
```

- [x] **Step 3: Push**

Run:

```bash
git push origin main
```

Expected: `main -> main`.
