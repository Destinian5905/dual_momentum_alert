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

## Telegram Command Bot On Oracle VPS

The GitHub Actions monthly alert can stay as-is. For Telegram commands, run `telegram_bot.py` continuously on the VPS.

Bot commands:

- `/help` or `/start`: show commands
- `/signal`: latest signal without backtest
- `/backtest`: latest signal with backtest recommendations
- `/config`: current config summary
- `/assets`: enabled asset list
- `/criteria`: enabled ranking criteria

Only the chat id in `TELEGRAM_CHAT_ID` is allowed to run commands.

Install on Ubuntu:

```bash
sudo apt update
sudo apt install -y git python3-venv python3-pip
sudo mkdir -p /opt
sudo chown ubuntu:ubuntu /opt
cd /opt
git clone https://github.com/Destinian5905/dual_momentum_alert.git dual_momentum_alert
cd /opt/dual_momentum_alert
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
cp dual_momentum_config.example.json dual_momentum_config.json
```

Create the environment file:

```bash
sudo nano /etc/dual-momentum-alert.env
```

Example:

```env
TELEGRAM_BOT_TOKEN=123456:replace-me
TELEGRAM_CHAT_ID=123456789
DUAL_MOMENTUM_CONFIG=/opt/dual_momentum_alert/dual_momentum_config.json
```

Secure it:

```bash
sudo chmod 600 /etc/dual-momentum-alert.env
```

Install and start the systemd service:

```bash
sudo cp deploy/dual-momentum-bot.service /etc/systemd/system/dual-momentum-bot.service
sudo systemctl daemon-reload
sudo systemctl enable --now dual-momentum-bot
```

Check status and logs:

```bash
sudo systemctl status dual-momentum-bot
journalctl -u dual-momentum-bot -f
```

Update after a new push:

```bash
cd /opt/dual_momentum_alert
git pull origin main
source .venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart dual-momentum-bot
```
