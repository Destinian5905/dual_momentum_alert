import argparse
import copy
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests
import yfinance as yf

try:
    import holidays
except ImportError:
    holidays = None


START_DATE = "2015-01-01"
BACKTEST_START_DATE = "1999-01-01"
TOP_N = 3
COUNTRY_FOR_BUSINESS_DAY = "KR"
FX_TICKER = "KRW=X"
OUTPUT_DIR = Path("output")


DEFAULT_ASSETS = [
    {"key": "SPY", "name": "SPY - S&P 500", "ticker": "SPY", "currency": "USD", "enabled": True},
    {"key": "QQQ", "name": "QQQ - Nasdaq 100", "ticker": "QQQ", "currency": "USD", "enabled": True},
    {"key": "VEA", "name": "VEA - Developed ex-US", "ticker": "VEA", "currency": "USD", "enabled": True},
    {"key": "VWO", "name": "VWO - Emerging Markets", "ticker": "VWO", "currency": "USD", "enabled": True},
    {"key": "KOREA", "name": "ACE 200 / KOSPI200 proxy", "ticker": "105190.KS", "currency": "KRW", "enabled": True},
    {"key": "VGLT", "name": "VGLT - Long-term US Treasury", "ticker": "VGLT", "currency": "USD", "enabled": True},
    {"key": "GLD", "name": "GLD - Gold proxy", "ticker": "GLD", "currency": "USD", "enabled": True},
    {"key": "PDBC", "name": "PDBC - Commodities", "ticker": "PDBC", "currency": "USD", "enabled": True},
    {"key": "UUP", "name": "UUP - US Dollar Index Bullish", "ticker": "UUP", "currency": "USD", "enabled": True},
    {"key": "SGOV", "name": "SGOV - 0-3M US Treasury", "ticker": "SGOV", "currency": "USD", "enabled": True},
]

CRITERIA_DEFINITIONS = {
    "return_1m": {"label": "1M return", "kind": "return", "window": 1, "higher_is_better": True},
    "return_3m": {"label": "3M return", "kind": "return", "window": 3, "higher_is_better": True},
    "return_6m": {"label": "6M return", "kind": "return", "window": 6, "higher_is_better": True},
    "return_9m": {"label": "9M return", "kind": "return", "window": 9, "higher_is_better": True},
    "return_12m": {"label": "12M return", "kind": "return", "window": 12, "higher_is_better": True},
    "sharpe_6m": {"label": "6M Sharpe", "kind": "sharpe", "window": 6, "higher_is_better": True},
    "sharpe_9m": {"label": "9M Sharpe", "kind": "sharpe", "window": 9, "higher_is_better": True},
    "sharpe_12m": {"label": "12M Sharpe", "kind": "sharpe", "window": 12, "higher_is_better": True},
    "sortino_6m": {"label": "6M Sortino", "kind": "sortino", "window": 6, "higher_is_better": True},
    "sortino_9m": {"label": "9M Sortino", "kind": "sortino", "window": 9, "higher_is_better": True},
    "sortino_12m": {"label": "12M Sortino", "kind": "sortino", "window": 12, "higher_is_better": True},
    "mdd_3m": {"label": "3M MDD", "kind": "mdd", "window": 3, "higher_is_better": True},
    "mdd_6m": {"label": "6M MDD", "kind": "mdd", "window": 6, "higher_is_better": True},
    "mdd_9m": {"label": "9M MDD", "kind": "mdd", "window": 9, "higher_is_better": True},
    "mdd_12m": {"label": "12M MDD", "kind": "mdd", "window": 12, "higher_is_better": True},
}

DEFAULT_CRITERIA = [
    {"id": "return_1m", "weight": 0.15, "enabled": True},
    {"id": "return_3m", "weight": 0.15, "enabled": True},
    {"id": "return_6m", "weight": 0.40, "enabled": True},
    {"id": "return_9m", "weight": 0.00, "enabled": False},
    {"id": "return_12m", "weight": 0.05, "enabled": True},
    {"id": "sharpe_6m", "weight": 0.00, "enabled": False},
    {"id": "sharpe_9m", "weight": 0.05, "enabled": True},
    {"id": "sharpe_12m", "weight": 0.05, "enabled": True},
    {"id": "sortino_9m", "weight": 0.10, "enabled": True},
    {"id": "sortino_12m", "weight": 0.05, "enabled": True},
    {"id": "mdd_6m", "weight": 0.00, "enabled": False},
    {"id": "mdd_12m", "weight": 0.00, "enabled": False},
]

DEFAULT_CONFIG = {
    "start_date": START_DATE,
    "backtest_start_date": BACKTEST_START_DATE,
    "top_n": TOP_N,
    "risk_free_asset": "SGOV",
    "assets": DEFAULT_ASSETS,
    "criteria": DEFAULT_CRITERIA,
    "backtest": {
        "enabled": True,
        "top_n_options": [1, 2, 3],
    },
}


def today_kst() -> date:
    return datetime.now(ZoneInfo("Asia/Seoul")).date()


def normalize_config(raw_config: dict | None = None) -> dict:
    config = copy.deepcopy(DEFAULT_CONFIG)
    raw_config = raw_config or {}

    for key in ("start_date", "backtest_start_date", "top_n", "risk_free_asset"):
        if key in raw_config:
            config[key] = raw_config[key]

    if "backtest" in raw_config:
        config["backtest"].update(raw_config["backtest"])

    if "assets" in raw_config:
        config["assets"] = raw_config["assets"]

    if "criteria" in raw_config:
        config["criteria"] = raw_config["criteria"]

    assets = {}
    for asset in config["assets"]:
        if not asset.get("enabled", True):
            continue
        key = str(asset["key"]).strip()
        ticker = str(asset["ticker"]).strip()
        currency = str(asset.get("currency", "USD")).strip().upper()
        if not key or not ticker:
            raise ValueError("Each enabled asset needs non-empty key and ticker.")
        if currency not in {"USD", "KRW"}:
            raise ValueError(f"Unsupported currency for {key}: {currency}. Use USD or KRW.")
        assets[key] = {
            "name": str(asset.get("name", key)),
            "ticker": ticker,
            "currency": currency,
        }

    criteria = []
    for criterion in config["criteria"]:
        if not criterion.get("enabled", True):
            continue
        criterion_id = str(criterion["id"]).strip()
        if criterion_id not in CRITERIA_DEFINITIONS:
            raise ValueError(f"Unknown criterion: {criterion_id}")
        weight = float(criterion.get("weight", 0.0))
        if weight <= 0:
            continue
        criteria.append({"id": criterion_id, "weight": weight})

    if not assets:
        raise ValueError("At least one asset must be enabled.")
    if not criteria:
        raise ValueError("At least one ranking criterion with positive weight must be enabled.")

    risk_free_asset = str(config.get("risk_free_asset", "SGOV")).strip()
    if risk_free_asset not in assets:
        raise ValueError(f"Risk-free proxy asset is not enabled: {risk_free_asset}")

    top_n = int(config.get("top_n", TOP_N))
    if top_n < 1 or top_n > len(assets):
        raise ValueError(f"top_n must be between 1 and enabled asset count ({len(assets)}).")

    config["assets"] = assets
    config["criteria"] = criteria
    config["top_n"] = top_n
    config["risk_free_asset"] = risk_free_asset
    return config


def load_config(path: str | None = None) -> dict:
    if not path:
        default_config_path = Path("dual_momentum_config.json")
        if default_config_path.exists():
            path = str(default_config_path)
        else:
            return normalize_config()

    if not path:
        return normalize_config()

    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with config_path.open("r", encoding="utf-8") as f:
        raw_config = json.load(f)

    return normalize_config(raw_config)


def get_korean_holidays(year: int):
    if holidays is None:
        return set()

    try:
        return set(holidays.KR(years=[year]).keys())
    except Exception:
        return set()


def is_business_day(d: date) -> bool:
    if d.weekday() >= 5:
        return False
    if COUNTRY_FOR_BUSINESS_DAY == "KR" and d in get_korean_holidays(d.year):
        return False
    return True


def is_second_business_day(d: date) -> bool:
    current = d.replace(day=1)
    business_days = []

    while current.month == d.month:
        if is_business_day(current):
            business_days.append(current)
        if len(business_days) >= 2:
            break
        current = current + pd.Timedelta(days=1)

    return len(business_days) >= 2 and d == business_days[1]


def download_adjusted_close(ticker: str, start_date: str = START_DATE) -> pd.Series:
    df = yf.download(
        ticker,
        start=start_date,
        auto_adjust=True,
        progress=False,
        threads=False,
    )

    if df.empty:
        raise ValueError(f"Data download failed: {ticker}")

    close = df["Close"]
    if isinstance(close, pd.DataFrame):
        if close.shape[1] == 0:
            raise ValueError(f"Close data is empty: {ticker}")
        close = close.iloc[:, 0]

    close = pd.to_numeric(close, errors="coerce").dropna()
    close.name = ticker
    if close.empty:
        raise ValueError(f"No valid price data: {ticker}")
    return close


def get_last_completed_month_end(today: date | None = None) -> pd.Timestamp:
    if today is None:
        today = date.today()
    first_day_this_month = pd.Timestamp(today.replace(day=1))
    return (first_day_this_month - pd.offsets.MonthEnd(1)).normalize()


def to_month_end(series: pd.Series) -> pd.Series:
    monthly = series.dropna().resample("ME").last().dropna()
    return monthly[monthly.index <= get_last_completed_month_end()]


def build_monthly_prices_krw(config: dict) -> tuple[pd.DataFrame, pd.Series]:
    start_date = min(str(config["start_date"]), str(config["backtest_start_date"]))
    fx_daily = download_adjusted_close(FX_TICKER, start_date=start_date)
    fx_monthly = to_month_end(fx_daily)
    fx_monthly.name = "USD_KRW"

    price_dict = {}
    for asset_key, info in config["assets"].items():
        daily_price = download_adjusted_close(info["ticker"], start_date=start_date)
        monthly_price = to_month_end(daily_price)

        if info["currency"] == "USD":
            temp = pd.concat(
                [monthly_price.rename("asset_price"), fx_monthly.rename("fx_rate")],
                axis=1,
                sort=False,
            ).dropna()
            if temp.empty:
                raise ValueError(f"No common monthly data for {asset_key} and USD/KRW.")
            krw_price = temp["asset_price"] * temp["fx_rate"]
        else:
            krw_price = monthly_price.copy()

        krw_price.name = asset_key
        price_dict[asset_key] = krw_price

    return pd.concat(price_dict.values(), axis=1).sort_index(), fx_monthly


def calc_monthly_returns(prices: pd.DataFrame) -> pd.DataFrame:
    return prices.pct_change()


def calc_cumulative_return(returns: pd.DataFrame, window: int) -> pd.DataFrame:
    return (1 + returns).rolling(window).apply(np.prod, raw=True) - 1


def calc_rolling_sharpe(returns: pd.DataFrame, rf_monthly: pd.Series, window: int) -> pd.DataFrame:
    excess = returns.sub(rf_monthly, axis=0)
    mean = excess.rolling(window).mean()
    std = excess.rolling(window).std()
    sharpe = mean / std
    sharpe = sharpe.replace([np.inf, -np.inf], np.nan)
    return sharpe.mask(std.abs() < 1e-12, 0.0)


def calc_rolling_sortino(returns: pd.DataFrame, rf_monthly: pd.Series, window: int) -> pd.DataFrame:
    excess = returns.sub(rf_monthly, axis=0)
    downside = excess.copy()
    downside[downside > 0] = 0.0
    downside_deviation = np.sqrt((downside**2).rolling(window).mean())
    sortino = excess.rolling(window).mean() / downside_deviation
    sortino = sortino.replace([np.inf, -np.inf], np.nan)
    return sortino.mask(downside_deviation.abs() < 1e-12, 0.0)


def calc_rolling_mdd(prices: pd.DataFrame, window: int) -> pd.DataFrame:
    def window_mdd(values: np.ndarray) -> float:
        peaks = np.maximum.accumulate(values)
        drawdowns = values / peaks - 1.0
        return float(np.min(drawdowns))

    return prices.rolling(window).apply(window_mdd, raw=True)


def calculate_metric(
    returns: pd.DataFrame,
    prices: pd.DataFrame,
    criterion_id: str,
    rf_monthly: pd.Series,
) -> pd.DataFrame:
    definition = CRITERIA_DEFINITIONS[criterion_id]
    kind = definition["kind"]
    window = int(definition["window"])

    if kind == "return":
        return calc_cumulative_return(returns, window)
    if kind == "sharpe":
        return calc_rolling_sharpe(returns, rf_monthly, window)
    if kind == "sortino":
        return calc_rolling_sortino(returns, rf_monthly, window)
    if kind == "mdd":
        return calc_rolling_mdd(prices, window)

    raise ValueError(f"Unsupported criterion kind: {kind}")


def rank_metric(metric: pd.DataFrame, definition: dict) -> pd.DataFrame:
    n = metric.shape[1]
    ranks = metric.rank(
        axis=1,
        ascending=not definition.get("higher_is_better", True),
        method="min",
        na_option="keep",
    )
    return (n + 1) - ranks


def calculate_total_score(
    prices_krw: pd.DataFrame,
    config: dict,
    criteria: list[dict] | None = None,
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame], dict[str, pd.DataFrame]]:
    assets = list(config["assets"].keys())
    missing_assets = [asset for asset in assets if asset not in prices_krw.columns]
    if missing_assets:
        raise ValueError(f"Missing price data for assets: {missing_assets}")

    prices_krw = prices_krw[assets].copy()
    returns = calc_monthly_returns(prices_krw)
    rf = returns[config["risk_free_asset"]].copy()
    active_criteria = criteria or config["criteria"]

    total_score = pd.DataFrame(0.0, index=prices_krw.index, columns=assets)
    score_frames = {}
    metric_frames = {}

    for criterion in active_criteria:
        criterion_id = criterion["id"]
        weight = float(criterion["weight"])
        metric = calculate_metric(returns, prices_krw, criterion_id, rf)
        score = rank_metric(metric, CRITERIA_DEFINITIONS[criterion_id])
        metric_frames[criterion_id] = metric
        score_frames[criterion_id] = score
        total_score = total_score.add(weight * score, fill_value=np.nan)

    valid_mask = pd.DataFrame(True, index=prices_krw.index, columns=assets)
    for score in score_frames.values():
        valid_mask &= score.notna()
    total_score = total_score.where(valid_mask)

    return total_score, score_frames, metric_frames


def calc_latest_signal(prices_krw: pd.DataFrame, config: dict) -> dict:
    assets = list(config["assets"].keys())
    prices_krw = prices_krw[assets].copy()
    returns = calc_monthly_returns(prices_krw)
    total_score, score_frames, metric_frames = calculate_total_score(prices_krw, config)
    complete_rows = total_score.dropna(how="any")

    if complete_rows.empty:
        last_date = total_score.index[-1]
        nan_assets = total_score.loc[last_date][total_score.loc[last_date].isna()].index.tolist()
        raise ValueError(
            "No month has valid scores for every enabled asset.\n"
            f"Most recent checked month: {last_date.strftime('%Y-%m-%d')}\n"
            f"Assets without scores: {nan_assets}"
        )

    latest_signal_date = complete_rows.index[-1]
    latest_scores = total_score.loc[latest_signal_date, assets]

    rows = []
    for asset in assets:
        row = {
            "asset": asset,
            "name": config["assets"][asset]["name"],
            "score_total": latest_scores[asset],
        }
        for criterion in config["criteria"]:
            criterion_id = criterion["id"]
            row[f"score_{criterion_id}"] = score_frames[criterion_id].loc[latest_signal_date, asset]
            row[criterion_id] = metric_frames[criterion_id].loc[latest_signal_date, asset]
        rows.append(row)

    detail = pd.DataFrame(rows).sort_values("score_total", ascending=False).reset_index(drop=True)
    detail.insert(0, "rank", np.arange(1, len(detail) + 1))
    top_assets = detail.head(config["top_n"]).set_index("asset")["score_total"]

    return {
        "signal_date": latest_signal_date,
        "top_assets": top_assets,
        "detail": detail,
        "returns": returns,
        "prices_krw": prices_krw,
        "total_score": total_score,
        "score_frames": score_frames,
        "metric_frames": metric_frames,
        "config": config,
    }


def annualized_return(monthly_returns: pd.Series) -> float:
    monthly_returns = monthly_returns.dropna()
    if monthly_returns.empty:
        return np.nan
    total = float((1 + monthly_returns).prod())
    years = len(monthly_returns) / 12
    if years <= 0 or total <= 0:
        return np.nan
    return total ** (1 / years) - 1


def annualized_sharpe(monthly_returns: pd.Series) -> float:
    monthly_returns = monthly_returns.dropna()
    std = monthly_returns.std()
    if monthly_returns.empty or pd.isna(std) or abs(std) < 1e-12:
        return np.nan
    return float(monthly_returns.mean() / std * np.sqrt(12))


def annualized_sortino(monthly_returns: pd.Series) -> float:
    monthly_returns = monthly_returns.dropna()
    downside = monthly_returns[monthly_returns < 0]
    downside_std = downside.std()
    if monthly_returns.empty or pd.isna(downside_std) or abs(downside_std) < 1e-12:
        return np.nan
    return float(monthly_returns.mean() / downside_std * np.sqrt(12))


def max_drawdown(monthly_returns: pd.Series) -> float:
    monthly_returns = monthly_returns.dropna()
    if monthly_returns.empty:
        return np.nan
    equity = (1 + monthly_returns).cumprod()
    drawdown = equity / equity.cummax() - 1
    return float(drawdown.min())


def run_backtest(prices_krw: pd.DataFrame, config: dict, criteria: list[dict], top_n: int, name: str) -> dict:
    total_score, _, _ = calculate_total_score(prices_krw, config, criteria=criteria)
    returns = calc_monthly_returns(prices_krw[list(config["assets"].keys())])
    shifted_scores = total_score.shift(1)
    strategy_returns = []

    for signal_date, row in shifted_scores.iterrows():
        if row.isna().any() or signal_date not in returns.index:
            strategy_returns.append(np.nan)
            continue
        selected_assets = row.sort_values(ascending=False).head(top_n).index
        strategy_returns.append(float(returns.loc[signal_date, selected_assets].mean()))

    strategy_returns = pd.Series(strategy_returns, index=shifted_scores.index, name=name).dropna()
    start = pd.Timestamp(config["backtest_start_date"])
    strategy_returns = strategy_returns[strategy_returns.index >= start]

    return {
        "strategy": name,
        "criteria": criteria,
        "top_n": top_n,
        "start": strategy_returns.index.min() if not strategy_returns.empty else pd.NaT,
        "end": strategy_returns.index.max() if not strategy_returns.empty else pd.NaT,
        "months": int(strategy_returns.shape[0]),
        "cagr": annualized_return(strategy_returns),
        "sharpe": annualized_sharpe(strategy_returns),
        "sortino": annualized_sortino(strategy_returns),
        "mdd": max_drawdown(strategy_returns),
        "monthly_returns": strategy_returns,
    }


def build_strategy_candidates(config: dict) -> list[dict]:
    base = {"name": "Current config", "criteria": config["criteria"]}
    candidates = [base]

    candidate_sets = [
        ("Return momentum", ["return_1m", "return_3m", "return_6m", "return_12m"]),
        ("Risk adjusted", ["sharpe_6m", "sharpe_12m", "sortino_6m", "sortino_12m"]),
        ("Drawdown defensive", ["return_6m", "return_12m", "mdd_6m", "mdd_12m"]),
        ("Balanced with MDD", ["return_3m", "return_6m", "sharpe_12m", "sortino_12m", "mdd_12m"]),
    ]

    for name, ids in candidate_sets:
        criteria = [{"id": criterion_id, "weight": 1 / len(ids)} for criterion_id in ids]
        candidates.append({"name": name, "criteria": criteria})

    return candidates


def evaluate_strategy_candidates(prices_krw: pd.DataFrame, config: dict) -> list[dict]:
    results = []
    assets_count = len(config["assets"])
    requested_options = config.get("backtest", {}).get("top_n_options", [config["top_n"]])
    top_n_options = sorted({int(n) for n in requested_options if 1 <= int(n) <= assets_count})
    if config["top_n"] not in top_n_options:
        top_n_options.append(config["top_n"])

    for candidate in build_strategy_candidates(config):
        for top_n in top_n_options:
            name = f"{candidate['name']} / top {top_n}"
            result = run_backtest(prices_krw, config, candidate["criteria"], top_n, name)
            if result["months"] > 0:
                results.append(result)

    return results


def select_backtest_recommendations(results: list[dict]) -> dict:
    if not results:
        return {}

    finite = [result for result in results if not pd.isna(result.get("cagr"))]
    if not finite:
        return {}

    def risk_adjusted_score(result: dict) -> float:
        sharpe = result.get("sharpe")
        sortino = result.get("sortino")
        parts = [value for value in (sharpe, sortino) if not pd.isna(value)]
        if not parts:
            return float("-inf")
        return float(np.mean(parts))

    return {
        "highest_cagr": max(finite, key=lambda result: result["cagr"]),
        "highest_risk_adjusted": max(finite, key=risk_adjusted_score),
        "lowest_mdd": max(finite, key=lambda result: result["mdd"] if not pd.isna(result["mdd"]) else float("-inf")),
    }


def format_pct(x: float) -> str:
    if pd.isna(x):
        return "N/A"
    return f"{x * 100:.2f}%"


def format_float(x: float) -> str:
    if pd.isna(x):
        return "N/A"
    return f"{x:.2f}"


def criterion_label(criterion_id: str) -> str:
    return CRITERIA_DEFINITIONS[criterion_id]["label"]


def build_message(signal: dict, backtest_results: list[dict] | None = None) -> str:
    config = signal["config"]
    signal_date = signal["signal_date"]
    detail = signal["detail"].copy()
    recommendations = select_backtest_recommendations(backtest_results or [])

    lines = []
    lines.append("Dual Momentum Monthly Signal")
    lines.append("")
    lines.append(f"Signal date: {signal_date.strftime('%Y-%m-%d')}")
    lines.append(f"Enabled assets: {len(config['assets'])}")
    lines.append("")
    lines.append("Ranking criteria:")
    for criterion in config["criteria"]:
        lines.append(f"- {criterion_label(criterion['id'])}: {criterion['weight'] * 100:.1f}%")
    lines.append("")
    lines.append("Ranking results:")
    lines.append("")

    for _, row in detail.iterrows():
        lines.append(f"{int(row['rank'])}. {row['asset']} | {row['name']}")
        lines.append(f">> Total score: {row['score_total']:.2f}")
        for criterion in config["criteria"]:
            criterion_id = criterion["id"]
            value = row[criterion_id]
            if CRITERIA_DEFINITIONS[criterion_id]["kind"] in {"return", "mdd"}:
                value_text = format_pct(value)
            else:
                value_text = format_float(value)
            lines.append(f"* {criterion_label(criterion_id)}: {value_text}")
        lines.append("")

    lines.append(f"Suggested allocation: equal weight among top {config['top_n']} assets")
    lines.append(f"Each selected asset: {100 / config['top_n']:.2f}%")

    if recommendations:
        lines.append("")
        lines.append("Backtest recommendations:")
        labels = {
            "highest_cagr": "Highest CAGR",
            "highest_risk_adjusted": "Highest Sharpe/Sortino",
            "lowest_mdd": "Lowest MDD",
        }
        for key, label in labels.items():
            result = recommendations[key]
            start = result["start"].strftime("%Y-%m-%d") if not pd.isna(result["start"]) else "N/A"
            end = result["end"].strftime("%Y-%m-%d") if not pd.isna(result["end"]) else "N/A"
            lines.append(
                f"- {label}: {result['strategy']} | "
                f"CAGR {format_pct(result['cagr'])}, "
                f"Sharpe {format_float(result['sharpe'])}, "
                f"Sortino {format_float(result['sortino'])}, "
                f"MDD {format_pct(result['mdd'])} ({start} to {end})"
            )

    lines.append("")
    lines.append("Note: Results are based on yfinance adjusted prices converted to KRW. Check prices, FX, taxes, and spreads before trading.")
    return "\n".join(lines)


def send_telegram_message(message: str):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        raise EnvironmentError("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is not set.")

    response = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data={"chat_id": chat_id, "text": message, "disable_web_page_preview": True},
        timeout=30,
    )

    if response.status_code != 200:
        raise RuntimeError(f"Telegram send failed: {response.status_code} / {response.text}")


def save_output(signal: dict, backtest_results: list[dict] | None = None) -> Path:
    OUTPUT_DIR.mkdir(exist_ok=True)
    today_str = datetime.now().strftime("%Y%m%d")
    output_file = OUTPUT_DIR / f"dual_momentum_signal_{today_str}.xlsx"

    with pd.ExcelWriter(output_file, engine="openpyxl") as writer:
        signal["detail"].to_excel(writer, sheet_name="Latest_Signal", index=False)
        signal["prices_krw"].to_excel(writer, sheet_name="Monthly_Prices_KRW")
        signal["returns"].to_excel(writer, sheet_name="Monthly_Returns_KRW")
        signal["total_score"].to_excel(writer, sheet_name="Total_Scores")

        if backtest_results:
            summary_rows = []
            for result in backtest_results:
                summary_rows.append(
                    {
                        "strategy": result["strategy"],
                        "top_n": result["top_n"],
                        "start": result["start"],
                        "end": result["end"],
                        "months": result["months"],
                        "cagr": result["cagr"],
                        "sharpe": result["sharpe"],
                        "sortino": result["sortino"],
                        "mdd": result["mdd"],
                    }
                )
            pd.DataFrame(summary_rows).to_excel(writer, sheet_name="Backtest_Summary", index=False)

            returns = pd.concat([result["monthly_returns"] for result in backtest_results], axis=1)
            returns.to_excel(writer, sheet_name="Backtest_Returns")

    return output_file


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Run even when today is not the second Korean business day.")
    parser.add_argument("--no-send", action="store_true", help="Create Excel output without sending Telegram.")
    parser.add_argument("--config", help="Path to a JSON config file for assets, criteria, and backtest options.")
    parser.add_argument("--skip-backtest", action="store_true", help="Skip strategy backtests and recommendations.")
    args = parser.parse_args()

    today = today_kst()
    if not args.force and not is_second_business_day(today):
        print(f"{today} is not the second Korean business day. Skipping.")
        return

    config = load_config(args.config)
    print("Downloading data and calculating signal.")
    prices_krw, _ = build_monthly_prices_krw(config)
    signal = calc_latest_signal(prices_krw, config)

    backtest_results = []
    if config.get("backtest", {}).get("enabled", True) and not args.skip_backtest:
        backtest_results = evaluate_strategy_candidates(prices_krw, config)

    output_file = save_output(signal, backtest_results)
    message = build_message(signal, backtest_results)

    print(message)
    print(f"\nExcel saved: {output_file}")

    if not args.no_send:
        send_telegram_message(message)
        print("Telegram alert sent.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        error_message = f"Dual momentum alert error:\n{e}"
        print(error_message, file=sys.stderr)
        try:
            send_telegram_message(error_message)
        except Exception:
            pass
        sys.exit(1)
