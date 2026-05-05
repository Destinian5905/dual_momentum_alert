# dual_momentum_alert

Monthly dual momentum ranking alert for Telegram. The script downloads Yahoo Finance prices, converts USD assets to KRW with `KRW=X`, ranks assets by configurable momentum/risk criteria, saves an Excel file, and sends a Telegram message.

## Run

```bash
pip install -r requirements.txt
python monthly_dual_momentum_alert.py --force --no-send
```

GitHub Actions still runs the default strategy automatically on the second Korean business day. Telegram sending requires these repository secrets:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

## Configure Assets And Criteria

Copy the example config and edit it:

```bash
cp dual_momentum_config.example.json dual_momentum_config.json
python monthly_dual_momentum_alert.py --force --no-send --config dual_momentum_config.json
```

When `dual_momentum_config.json` exists in the repository, the script loads it automatically. That means GitHub Actions will use the edited config without changing the workflow file.

Set `"enabled": false` to remove an asset or criterion. Add any Yahoo Finance ticker by appending an asset object:

```json
{ "key": "SLV", "name": "SLV - Silver proxy", "ticker": "SLV", "currency": "USD", "enabled": true }
```

Supported currencies are `USD` and `KRW`. USD assets are converted to KRW using `KRW=X`. The `risk_free_asset` must stay enabled because Sharpe and Sortino use it as the risk-free proxy.

Supported ranking criteria:

- `return_1m`, `return_3m`, `return_6m`, `return_9m`, `return_12m`
- `sharpe_6m`, `sharpe_9m`, `sharpe_12m`
- `sortino_6m`, `sortino_9m`, `sortino_12m`
- `mdd_3m`, `mdd_6m`, `mdd_9m`, `mdd_12m`

MDD values are negative drawdowns, so smaller losses rank higher.

## Backtests

Backtests start from `backtest_start_date` when enough data exists for the enabled assets and criteria. The Telegram message and Excel output include three recommended strategies:

- Highest CAGR
- Highest Sharpe/Sortino
- Lowest MDD

Skip this section for faster manual runs:

```bash
python monthly_dual_momentum_alert.py --force --no-send --skip-backtest
```
