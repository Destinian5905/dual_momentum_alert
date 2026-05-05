# Telegram VPS Bot Design

## Goal

Run the dual momentum program as a long-running Telegram bot on an Oracle VPS while keeping the existing GitHub Actions monthly alert flow intact.

## Recommended Approach

Add a new `telegram_bot.py` entrypoint instead of mixing polling logic into `monthly_dual_momentum_alert.py`. The current script remains the batch runner used by GitHub Actions. The new bot imports the existing config and signal functions, runs calculations on demand, and replies in Telegram.

## Commands

- `/help` and `/start`: show available commands.
- `/signal`: calculate the latest signal without backtest recommendations.
- `/backtest`: calculate the latest signal with backtest recommendations.
- `/config`: show start dates, `top_n`, risk-free proxy, and whether backtesting is enabled.
- `/assets`: show enabled assets and Yahoo Finance tickers.
- `/criteria`: show enabled ranking criteria and weights.

## Authorization

The bot only accepts commands from the chat id stored in `TELEGRAM_CHAT_ID`. Commands from other chats receive a short unauthorized response and do not run downloads or backtests.

## Runtime

The VPS runs `python telegram_bot.py` under systemd. Environment variables are loaded from `/etc/dual-momentum-alert.env`:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- optional `DUAL_MOMENTUM_CONFIG`

## Data Flow

Telegram command -> authorization check -> existing config loader -> existing signal/backtest functions -> Telegram replies. Long calculations run in a background thread through `asyncio.to_thread` so the bot event loop stays responsive.

## Error Handling

Command handlers catch exceptions and send the error text back to the authorized chat. Long Telegram messages are split below Telegram's message size limit.

## Testing

Unit tests cover authorization, message splitting, and command summary formatting without importing the real Telegram library. Existing configurable momentum tests continue to cover ranking and backtest recommendation behavior.
