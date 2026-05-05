import asyncio
import os
from collections.abc import Iterable

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


def help_message() -> str:
    return "\n".join(
        [
            "Dual Momentum Bot Commands",
            "/signal - latest signal without backtest",
            "/backtest - latest signal with backtest recommendations",
            "/config - current config summary",
            "/assets - enabled asset list",
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


def validate_environment(required_keys: Iterable[str] = ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")):
    missing = [key for key in required_keys if not os.environ.get(key)]
    if missing:
        raise EnvironmentError(f"Missing required environment variables: {', '.join(missing)}")


def build_application():
    from telegram.ext import Application, CommandHandler

    validate_environment()
    app = Application.builder().token(os.environ["TELEGRAM_BOT_TOKEN"]).build()
    app.add_handler(CommandHandler("start", require_authorized(start_command)))
    app.add_handler(CommandHandler("help", require_authorized(help_command)))
    app.add_handler(CommandHandler("signal", require_authorized(signal_command)))
    app.add_handler(CommandHandler("backtest", require_authorized(backtest_command)))
    app.add_handler(CommandHandler("config", require_authorized(config_command)))
    app.add_handler(CommandHandler("assets", require_authorized(assets_command)))
    app.add_handler(CommandHandler("criteria", require_authorized(criteria_command)))
    return app


def main():
    application = build_application()
    application.run_polling(allowed_updates=["message"])


if __name__ == "__main__":
    main()
