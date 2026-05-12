import asyncio
import copy
import json
import os
import re
import shutil
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

import monthly_dual_momentum_alert as momentum


DEFAULT_MESSAGE_LIMIT = 3900


def split_message(message: str, limit: int = DEFAULT_MESSAGE_LIMIT) -> list[str]:
    if limit < 1:
        raise ValueError("limit must be positive")
    if not message:
        return [""]

    chunks = []
    remaining = message
    while len(remaining) > limit:
        split_at = remaining.rfind("\n", 0, limit + 1)
        if split_at <= 0:
            split_at = limit
        chunks.append(remaining[:split_at])
        remaining = remaining[split_at:].lstrip("\n")
    chunks.append(remaining)
    return chunks


def is_authorized_chat(chat_id: int | None, expected_chat_id: str | None) -> bool:
    if chat_id is None or not expected_chat_id:
        return False
    return str(chat_id) == str(expected_chat_id)


def format_config_summary(config: dict) -> str:
    backtest_enabled = config.get("backtest", {}).get("enabled", True)
    return "\n".join(
        [
            "Current config",
            f"start_date: {config['start_date']}",
            f"backtest_start_date: {config['backtest_start_date']}",
            f"top_n: {config['top_n']}",
            f"risk_free_asset: {config['risk_free_asset']}",
            f"backtest_enabled: {backtest_enabled}",
            f"enabled_assets: {len(config['assets'])}",
            f"enabled_criteria: {len(config['criteria'])}",
        ]
    )


def format_assets(config: dict) -> str:
    lines = ["Enabled assets"]
    for key, asset in config["assets"].items():
        lines.append(f"- {key}: {asset['ticker']} | {asset['name']} | {asset['currency']}")
    return "\n".join(lines)


def format_criteria(config: dict) -> str:
    lines = ["Enabled criteria"]
    for criterion in config["criteria"]:
        label = momentum.CRITERIA_DEFINITIONS[criterion["id"]]["label"]
        lines.append(f"- {criterion['id']}: {label}, weight {criterion['weight'] * 100:.1f}%")
    return "\n".join(lines)


def normalize_ticker(ticker: str) -> str:
    normalized = ticker.strip().upper()
    if not normalized:
        raise ValueError("Ticker is required.")
    if not re.fullmatch(r"[A-Z0-9.^=\-]+", normalized):
        raise ValueError("Ticker may only contain letters, numbers, dot, caret, equals, and hyphen.")
    return normalized


def asset_key_from_ticker(ticker: str) -> str:
    ticker = normalize_ticker(ticker)
    key = re.sub(r"[^A-Z0-9]+", "_", ticker).strip("_")
    return key or ticker


def infer_currency(ticker: str) -> str:
    ticker = normalize_ticker(ticker)
    if ticker.endswith((".KS", ".KQ")):
        return "KRW"
    return "USD"


def build_asset_entry(ticker: str, name: str | None = None) -> dict:
    ticker = normalize_ticker(ticker)
    return {
        "key": asset_key_from_ticker(ticker),
        "name": name or ticker,
        "ticker": ticker,
        "currency": infer_currency(ticker),
        "asset_class": "UNCLASSIFIED",
        "enabled": True,
    }


def normalize_asset_class(name: str) -> str:
    value = name.strip().upper()
    if not re.fullmatch(r"[A-Z0-9_\-]+", value):
        raise ValueError("Asset class may only include letters, numbers, underscore, hyphen.")
    return value


def set_asset_class_enabled(raw_config: dict, class_name: str, enabled: bool) -> dict:
    updated = copy.deepcopy(raw_config)
    class_name = normalize_asset_class(class_name)
    touched = 0
    for i, asset in enumerate(updated.get("assets", [])):
        if normalize_asset_class(str(asset.get("asset_class", "UNCLASSIFIED"))) == class_name:
            updated["assets"][i] = {**asset, "enabled": enabled}
            touched += 1
    if touched == 0:
        raise ValueError(f"Asset class not found: {class_name}")
    return repair_config_after_asset_change(updated)


def asset_ticker(asset: dict) -> str:
    return normalize_ticker(str(asset.get("ticker", "")))


def find_asset_by_ticker(raw_config: dict, ticker: str) -> tuple[int, dict] | tuple[None, None]:
    ticker = normalize_ticker(ticker)
    for index, asset in enumerate(raw_config.get("assets", [])):
        try:
            if asset_ticker(asset) == ticker:
                return index, asset
        except ValueError:
            continue
    return None, None


def enabled_asset_keys(raw_config: dict) -> list[str]:
    return [
        str(asset.get("key"))
        for asset in raw_config.get("assets", [])
        if asset.get("enabled", True) and asset.get("key")
    ]


def repair_config_after_asset_change(raw_config: dict) -> dict:
    enabled_keys = enabled_asset_keys(raw_config)
    if enabled_keys:
        if raw_config.get("risk_free_asset") not in enabled_keys:
            raw_config["risk_free_asset"] = enabled_keys[0]
        raw_config["top_n"] = max(1, min(int(raw_config.get("top_n", 1)), len(enabled_keys)))
    return raw_config


def apply_asset_add(raw_config: dict, asset_entry: dict) -> dict:
    updated = copy.deepcopy(raw_config)
    updated.setdefault("assets", [])
    index, existing = find_asset_by_ticker(updated, asset_entry["ticker"])
    if existing is None:
        used_keys = {str(asset.get("key")) for asset in updated["assets"]}
        candidate = copy.deepcopy(asset_entry)
        base_key = candidate["key"]
        suffix = 2
        while candidate["key"] in used_keys:
            candidate["key"] = f"{base_key}_{suffix}"
            suffix += 1
        updated["assets"].append(candidate)
    else:
        updated["assets"][index] = {**existing, **asset_entry, "key": existing.get("key", asset_entry["key"])}
    return repair_config_after_asset_change(updated)


def apply_asset_remove(raw_config: dict, ticker: str) -> dict:
    updated = copy.deepcopy(raw_config)
    index, existing = find_asset_by_ticker(updated, ticker)
    if existing is None:
        raise ValueError(f"Asset not found: {ticker}")
    updated["assets"][index] = {**existing, "enabled": False}
    return repair_config_after_asset_change(updated)


def editable_config_path() -> Path:
    configured = get_config_path()
    if configured:
        path = Path(configured)
    else:
        path = Path("dual_momentum_config.json")
    if not path.exists():
        raise FileNotFoundError(
            f"Editable config file not found: {path}. Copy dual_momentum_config.example.json first."
        )
    return path


def read_raw_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_config_with_backup(path: Path, raw_config: dict) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    backup_path = path.with_name(f"{path.name}.bak.{timestamp}")
    shutil.copy2(path, backup_path)
    with path.open("w", encoding="utf-8") as f:
        json.dump(raw_config, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return backup_path


def describe_asset_action(raw_config: dict, ticker: str) -> dict:
    ticker = normalize_ticker(ticker)
    _, existing = find_asset_by_ticker(raw_config, ticker)
    if existing is not None and existing.get("enabled", True):
        return {
            "action": "remove",
            "ticker": ticker,
            "name": existing.get("name", ticker),
            "currency": existing.get("currency", infer_currency(ticker)),
        }
    return {
        "action": "add",
        "ticker": ticker,
        "name": ticker,
        "currency": infer_currency(ticker),
    }


def fetch_asset_name(ticker: str) -> str:
    ticker = normalize_ticker(ticker)
    daily = momentum.download_adjusted_close(ticker, start_date="2020-01-01")
    if daily.empty:
        raise ValueError(f"No price data found for {ticker}")
    return ticker


def help_message() -> str:
    return "\n".join(
        [
            "Dual Momentum Bot Commands",
            "/signal - latest signal without backtest",
            "/backtest - latest signal with backtest recommendations",
            "/config - current config summary",
            "/assets - enabled asset list",
            "/asset TICKER - add or remove a ticker after confirmation",
            "/include_class CLASS - enable all assets in class",
            "/exclude_class CLASS - disable all assets in class",
            "/include_asset CLASS TICKER - add/enable ticker in class",
            "/exclude_asset CLASS TICKER - disable ticker in class",
            "/criteria - enabled ranking criteria",
            "/help - show this help",
        ]
    )


def get_config_path() -> str | None:
    return os.environ.get("DUAL_MOMENTUM_CONFIG")


def get_authorized_chat_id() -> str | None:
    return os.environ.get("TELEGRAM_CHAT_ID")


async def reply_chunks(update, text: str):
    for chunk in split_message(text):
        await update.message.reply_text(chunk, disable_web_page_preview=True)


async def reject_unauthorized(update):
    await update.message.reply_text("Unauthorized chat.")


def effective_chat_id(update) -> int | None:
    chat = getattr(update, "effective_chat", None)
    return getattr(chat, "id", None)


def require_authorized(handler):
    async def wrapped(update, context):
        if not is_authorized_chat(effective_chat_id(update), get_authorized_chat_id()):
            await reject_unauthorized(update)
            return
        await handler(update, context)

    return wrapped


async def start_command(update, context):
    await reply_chunks(update, help_message())


async def help_command(update, context):
    await reply_chunks(update, help_message())


async def config_command(update, context):
    config = momentum.load_config(get_config_path())
    await reply_chunks(update, format_config_summary(config))


async def assets_command(update, context):
    config = momentum.load_config(get_config_path())
    await reply_chunks(update, format_assets(config))


async def criteria_command(update, context):
    config = momentum.load_config(get_config_path())
    await reply_chunks(update, format_criteria(config))


async def asset_command(update, context):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    if not context.args:
        await update.message.reply_text("Usage: /asset TICKER\nExample: /asset SGOV")
        return

    try:
        ticker = normalize_ticker(context.args[0])
        config_path = editable_config_path()
        raw_config = read_raw_config(config_path)
        action = describe_asset_action(raw_config, ticker)
        if action["action"] == "add":
            action["name"] = await asyncio.to_thread(fetch_asset_name, ticker)
            text = (
                f"{ticker} is not active in the config.\n"
                f"Add it as {action['currency']} asset?"
            )
        else:
            text = (
                f"{ticker} is already active: {action['name']}.\n"
                "Remove it from active assets?"
            )
    except Exception as exc:
        await update.message.reply_text(f"Asset check failed:\n{exc}")
        return

    callback_data = f"asset:{action['action']}:{ticker}"
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Approve", callback_data=callback_data),
                InlineKeyboardButton("Cancel", callback_data=f"asset:cancel:{ticker}"),
            ]
        ]
    )
    await update.message.reply_text(text, reply_markup=keyboard)


async def asset_callback(update, context):
    query = update.callback_query
    if not is_authorized_chat(getattr(query.message.chat, "id", None), get_authorized_chat_id()):
        await query.answer("Unauthorized", show_alert=True)
        return

    await query.answer()
    parts = query.data.split(":", 2)
    if len(parts) != 3 or parts[0] != "asset":
        return

    action, ticker = parts[1], parts[2]
    if action == "cancel":
        await query.edit_message_text(f"Cancelled {ticker}.")
        return

    try:
        config_path = editable_config_path()
        raw_config = read_raw_config(config_path)
        if action == "add":
            name = await asyncio.to_thread(fetch_asset_name, ticker)
            updated = apply_asset_add(raw_config, build_asset_entry(ticker, name))
            verb = "Added"
        elif action == "remove":
            updated = apply_asset_remove(raw_config, ticker)
            verb = "Removed"
        else:
            await query.edit_message_text("Unknown asset action.")
            return
        momentum.normalize_config(updated)
        backup_path = write_config_with_backup(config_path, updated)
    except Exception as exc:
        await query.edit_message_text(f"Asset update failed:\n{exc}")
        return

    await query.edit_message_text(
        f"{verb} {ticker}.\n"
        f"Config saved: {config_path}\n"
        f"Backup saved: {backup_path}\n"
        f"risk_free_asset: {updated.get('risk_free_asset')}\n"
        f"top_n: {updated.get('top_n')}"
    )


async def run_report_command(update, include_backtest: bool):
    mode = "backtest" if include_backtest else "signal"
    await update.message.reply_text(f"Calculating {mode}. This can take a bit.")
    try:
        result = await asyncio.to_thread(
            momentum.generate_report,
            get_config_path(),
            include_backtest,
            True,
        )
    except Exception as exc:
        await reply_chunks(update, f"Calculation failed:\n{exc}")
        return

    await reply_chunks(update, result["message"])
    if result["output_file"] is not None:
        await update.message.reply_text(f"Excel saved on VPS: {result['output_file']}")


async def signal_command(update, context):
    await run_report_command(update, include_backtest=False)


async def backtest_command(update, context):
    await run_report_command(update, include_backtest=True)


async def include_class_command(update, context):
    if len(context.args) != 1:
        await update.message.reply_text("Usage: /include_class CLASS")
        return
    config_path = editable_config_path()
    raw = read_raw_config(config_path)
    updated = set_asset_class_enabled(raw, context.args[0], True)
    write_config_with_backup(config_path, updated)
    await update.message.reply_text("Class enabled.")


async def exclude_class_command(update, context):
    if len(context.args) != 1:
        await update.message.reply_text("Usage: /exclude_class CLASS")
        return
    config_path = editable_config_path()
    raw = read_raw_config(config_path)
    updated = set_asset_class_enabled(raw, context.args[0], False)
    write_config_with_backup(config_path, updated)
    await update.message.reply_text("Class disabled.")


async def include_asset_command(update, context):
    if len(context.args) != 2:
        await update.message.reply_text("Usage: /include_asset CLASS TICKER")
        return
    class_name, ticker = normalize_asset_class(context.args[0]), normalize_ticker(context.args[1])
    config_path = editable_config_path()
    raw = read_raw_config(config_path)
    entry = build_asset_entry(ticker, ticker)
    entry["asset_class"] = class_name
    updated = apply_asset_add(raw, entry)
    write_config_with_backup(config_path, updated)
    await update.message.reply_text(f"Asset included: {class_name} {ticker}")


async def exclude_asset_command(update, context):
    if len(context.args) != 2:
        await update.message.reply_text("Usage: /exclude_asset CLASS TICKER")
        return
    _, ticker = normalize_asset_class(context.args[0]), normalize_ticker(context.args[1])
    config_path = editable_config_path()
    raw = read_raw_config(config_path)
    updated = apply_asset_remove(raw, ticker)
    write_config_with_backup(config_path, updated)
    await update.message.reply_text(f"Asset disabled: {ticker}")


def validate_environment(required_keys: Iterable[str] = ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")):
    missing = [key for key in required_keys if not os.environ.get(key)]
    if missing:
        raise EnvironmentError(f"Missing required environment variables: {', '.join(missing)}")


def build_application():
    from telegram.ext import Application, CallbackQueryHandler, CommandHandler

    validate_environment()
    app = Application.builder().token(os.environ["TELEGRAM_BOT_TOKEN"]).build()
    app.add_handler(CommandHandler("start", require_authorized(start_command)))
    app.add_handler(CommandHandler("help", require_authorized(help_command)))
    app.add_handler(CommandHandler("signal", require_authorized(signal_command)))
    app.add_handler(CommandHandler("backtest", require_authorized(backtest_command)))
    app.add_handler(CommandHandler("config", require_authorized(config_command)))
    app.add_handler(CommandHandler("assets", require_authorized(assets_command)))
    app.add_handler(CommandHandler("asset", require_authorized(asset_command)))
    app.add_handler(CommandHandler("include_class", require_authorized(include_class_command)))
    app.add_handler(CommandHandler("exclude_class", require_authorized(exclude_class_command)))
    app.add_handler(CommandHandler("include_asset", require_authorized(include_asset_command)))
    app.add_handler(CommandHandler("exclude_asset", require_authorized(exclude_asset_command)))
    app.add_handler(CommandHandler("criteria", require_authorized(criteria_command)))
    app.add_handler(CallbackQueryHandler(asset_callback, pattern=r"^asset:"))
    return app


def main():
    application = build_application()
    application.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
