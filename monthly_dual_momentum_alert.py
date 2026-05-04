import os
import sys
import argparse
from pathlib import Path
from datetime import date, datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import yfinance as yf
import requests

try:
    import holidays
except ImportError:
    holidays = None


# =====================================================
# 1. 사용자 설정
# =====================================================

START_DATE = "2015-01-01"

# =====================================================
# 전략 비중: 1999.01~2026.04 장기 프록시 최적화 결과
# =====================================================

WEIGHT_1M_RETURN = 0.15
WEIGHT_3M_RETURN = 0.15
WEIGHT_6M_RETURN = 0.40
WEIGHT_9M_RETURN = 0.00
WEIGHT_12M_RETURN = 0.05

WEIGHT_6M_SHARPE = 0.00
WEIGHT_9M_SHARPE = 0.05
WEIGHT_12M_SHARPE = 0.05

WEIGHT_9M_SORTINO = 0.10
WEIGHT_12M_SORTINO = 0.05

TOP_N = 3

# 한국 기준 두 번째 영업일에만 알림
COUNTRY_FOR_BUSINESS_DAY = "KR"

# 결과 저장 폴더
OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

# 10개 자산
# name: 화면에 표시할 이름
# ticker: yfinance 티커
# currency: USD 또는 KRW
ASSETS = {
    "SPY": {
        "name": "SPY - S&P 500",
        "ticker": "SPY",
        "currency": "USD",
    },
    "QQQ": {
        "name": "QQQ - Nasdaq 100",
        "ticker": "QQQ",
        "currency": "USD",
    },
    "VEA": {
        "name": "VEA - Developed ex-US",
        "ticker": "VEA",
        "currency": "USD",
    },
    "VWO": {
        "name": "VWO - Emerging Markets",
        "ticker": "VWO",
        "currency": "USD",
    },
    "KOREA": {
        "name": "ACE 200 / KOSPI200 proxy",
        "ticker": "105190.KS",
        "currency": "KRW",
    },
    "VGLT": {
        "name": "VGLT - Long-term US Treasury",
        "ticker": "VGLT",
        "currency": "USD",
    },
    "GLD": {
        "name": "GLD - Gold proxy",
        "ticker": "GLD",
        "currency": "USD",
    },
    "PDBC": {
        "name": "PDBC - Commodities",
        "ticker": "PDBC",
        "currency": "USD",
    },
    "UUP": {
        "name": "UUP - US Dollar Index Bullish",
        "ticker": "UUP",
        "currency": "USD",
    },
    "SGOV": {
        "name": "SGOV - 0-3M US Treasury",
        "ticker": "SGOV",
        "currency": "USD",
    },
}

# USD/KRW 환율
FX_TICKER = "KRW=X"


# =====================================================
# 2. 영업일 판정
# =====================================================

def today_kst() -> date:
    return datetime.now(ZoneInfo("Asia/Seoul")).date()


def get_korean_holidays(year: int):
    """
    한국 공휴일 목록.
    holidays 패키지가 있으면 사용하고, 없으면 주말만 제외.
    """
    if holidays is None:
        return set()

    try:
        return set(holidays.KR(years=[year]).keys())
    except Exception:
        return set()


def is_business_day(d: date) -> bool:
    """
    한국 기준 영업일.
    주말 제외 + holidays 패키지가 있으면 한국 공휴일 제외.
    """
    if d.weekday() >= 5:
        return False

    if COUNTRY_FOR_BUSINESS_DAY == "KR":
        kr_holidays = get_korean_holidays(d.year)
        if d in kr_holidays:
            return False

    return True


def is_second_business_day(d: date) -> bool:
    """
    해당 날짜가 그 달의 두 번째 영업일인지 확인.
    """
    first_day = d.replace(day=1)
    current = first_day
    business_days = []

    while current.month == d.month:
        if is_business_day(current):
            business_days.append(current)

        if len(business_days) >= 2:
            break

        current = current + pd.Timedelta(days=1)

    if len(business_days) < 2:
        return False

    return d == business_days[1]


# =====================================================
# 3. 데이터 다운로드
# =====================================================

def download_adjusted_close(ticker: str, start_date: str = START_DATE) -> pd.Series:
    """
    yfinance에서 조정가격 성격의 Close를 다운로드.
    반환값은 반드시 pandas Series가 되도록 강제한다.
    """
    df = yf.download(
        ticker,
        start=start_date,
        auto_adjust=True,
        progress=False,
        threads=False,
    )

    if df.empty:
        raise ValueError(f"데이터 다운로드 실패: {ticker}")

    close = df["Close"]

    # yfinance 버전에 따라 Close가 DataFrame으로 반환될 수 있음
    if isinstance(close, pd.DataFrame):
        if close.shape[1] == 0:
            raise ValueError(f"Close 데이터가 비어 있습니다: {ticker}")
        close = close.iloc[:, 0]

    close = pd.to_numeric(close, errors="coerce")
    close = close.dropna()
    close.name = ticker

    if close.empty:
        raise ValueError(f"유효한 가격 데이터 없음: {ticker}")

    return close


def get_last_completed_month_end(today: date | None = None) -> pd.Timestamp:
    """
    오늘 기준으로 마지막으로 완전히 종료된 월말 날짜를 반환.
    예: 2026-04-26 실행 → 2026-03-31
        2026-05-02 실행 → 2026-04-30
    """
    if today is None:
        today = date.today()

    first_day_this_month = pd.Timestamp(today.replace(day=1))
    last_completed_month_end = first_day_this_month - pd.offsets.MonthEnd(1)

    return last_completed_month_end.normalize()


def to_month_end(series: pd.Series) -> pd.Series:
    """
    일별 가격을 월말 가격으로 변환.
    단, 아직 끝나지 않은 이번 달 데이터는 제외한다.
    """
    monthly = series.dropna().resample("ME").last().dropna()

    last_completed_month_end = get_last_completed_month_end()
    monthly = monthly[monthly.index <= last_completed_month_end]

    return monthly


def build_monthly_prices_krw() -> tuple[pd.DataFrame, pd.Series]:
    """
    10개 자산의 원화 기준 월말 가격 생성.
    USD 자산은 USD 가격 × USD/KRW 환율.
    KRW 자산은 그대로 사용.
    """
    fx_daily = download_adjusted_close(FX_TICKER)
    fx_monthly = to_month_end(fx_daily)
    fx_monthly.name = "USD_KRW"

    price_dict = {}

    for asset_key, info in ASSETS.items():
        ticker = info["ticker"]
        currency = info["currency"]

        daily_price = download_adjusted_close(ticker)
        monthly_price = to_month_end(daily_price)
        monthly_price.name = "asset_price"

        if currency == "USD":
            temp = pd.concat(
                [
                    monthly_price.rename("asset_price"),
                    fx_monthly.rename("fx_rate"),
                ],
                axis=1,
            ).dropna()

            if temp.empty:
                raise ValueError(f"{asset_key}와 USD/KRW 환율의 공통 월별 데이터가 없습니다.")

            krw_price = temp["asset_price"] * temp["fx_rate"]

        elif currency == "KRW":
            krw_price = monthly_price.copy()

        else:
            raise ValueError(f"알 수 없는 통화: {currency}")

        krw_price.name = asset_key
        price_dict[asset_key] = krw_price

    prices_krw = pd.concat(price_dict.values(), axis=1).sort_index()

    return prices_krw, fx_monthly


# =====================================================
# 4. 신호 계산
# =====================================================

def calc_monthly_returns(prices: pd.DataFrame) -> pd.DataFrame:
    return prices.pct_change()


def calc_cumulative_return(returns: pd.DataFrame, window: int) -> pd.DataFrame:
    """
    최근 n개월 누적수익률.
    """
    return (1 + returns).rolling(window).apply(np.prod, raw=True) - 1


def calc_rolling_sharpe(
    returns: pd.DataFrame,
    rf_monthly: pd.Series,
    window: int = 6,
) -> pd.DataFrame:
    """
    최근 n개월 샤프지수.
    SGOV를 무위험수익률 프록시로 사용할 경우,
    SGOV 자신의 초과수익률은 항상 0이므로 표준편차가 0이 된다.
    이 경우 샤프지수는 계산 불능이므로 0으로 처리한다.
    """
    excess = returns.sub(rf_monthly, axis=0)

    mean = excess.rolling(window).mean()
    std = excess.rolling(window).std()

    sharpe = mean / std
    sharpe = sharpe.replace([np.inf, -np.inf], np.nan)

    zero_std_mask = std.abs() < 1e-12
    sharpe = sharpe.mask(zero_std_mask, 0.0)

    return sharpe


def calc_rolling_sortino(
    returns: pd.DataFrame,
    rf_monthly: pd.Series,
    window: int = 12,
) -> pd.DataFrame:
    """
    최근 n개월 소르티노 지수.
    초과수익률 중 음수 구간만 하락위험으로 계산한다.

    Sortino = 평균 초과수익률 / 하락편차

    하락편차가 0이면 계산 불능이므로 0으로 처리한다.
    """
    excess = returns.sub(rf_monthly, axis=0)

    downside = excess.copy()
    downside[downside > 0] = 0.0

    mean_excess = excess.rolling(window).mean()
    downside_deviation = np.sqrt((downside ** 2).rolling(window).mean())

    sortino = mean_excess / downside_deviation
    sortino = sortino.replace([np.inf, -np.inf], np.nan)

    zero_downside_mask = downside_deviation.abs() < 1e-12
    sortino = sortino.mask(zero_downside_mask, 0.0)

    return sortino


def rank_score(df: pd.DataFrame) -> pd.DataFrame:
    """
    각 월별로 큰 값일수록 높은 점수.
    10개 자산 기준:
    1등 = 10점, 10등 = 1점.

    NaN은 순위 계산에서 제외되며, 해당 자산 점수도 NaN으로 남긴다.
    """
    n = df.shape[1]
    ranks = df.rank(axis=1, ascending=False, method="min", na_option="keep")
    scores = (n + 1) - ranks
    return scores


def calc_latest_signal(prices_krw: pd.DataFrame) -> dict:
    """
    최신 완성 월말 기준으로 1/3/6/9/12개월 수익률,
    6/9/12개월 샤프지수,
    9/12개월 소르티노 지수를 계산하고 전체 10개 자산을 평가한다.
    """
    expected_assets = list(ASSETS.keys())

    missing_assets = [a for a in expected_assets if a not in prices_krw.columns]
    if missing_assets:
        raise ValueError(f"가격 데이터에 누락된 자산이 있습니다: {missing_assets}")

    prices_krw = prices_krw[expected_assets].copy()
    returns = calc_monthly_returns(prices_krw)

    if "SGOV" not in returns.columns:
        raise ValueError("SGOV가 없어서 무위험수익률 프록시를 만들 수 없습니다.")

    # 현재 운용 코드에서는 SGOV 원화 월간 수익률을 무위험수익률 프록시로 사용
    rf = returns["SGOV"].copy()

    # -------------------------------------------------
    # 1. 수익률 지표
    # -------------------------------------------------
    r1 = calc_cumulative_return(returns, 1)
    r3 = calc_cumulative_return(returns, 3)
    r6 = calc_cumulative_return(returns, 6)
    r9 = calc_cumulative_return(returns, 9)
    r12 = calc_cumulative_return(returns, 12)

    # -------------------------------------------------
    # 2. 샤프지수
    # -------------------------------------------------
    sharpe6 = calc_rolling_sharpe(returns, rf, 6)
    sharpe9 = calc_rolling_sharpe(returns, rf, 9)
    sharpe12 = calc_rolling_sharpe(returns, rf, 12)

    # -------------------------------------------------
    # 3. 소르티노 지수
    # -------------------------------------------------
    sortino9 = calc_rolling_sortino(returns, rf, 9)
    sortino12 = calc_rolling_sortino(returns, rf, 12)

    # -------------------------------------------------
    # 4. 순위 점수화
    # -------------------------------------------------
    score_r1 = rank_score(r1)
    score_r3 = rank_score(r3)
    score_r6 = rank_score(r6)
    score_r9 = rank_score(r9)
    score_r12 = rank_score(r12)

    score_sharpe6 = rank_score(sharpe6)
    score_sharpe9 = rank_score(sharpe9)
    score_sharpe12 = rank_score(sharpe12)

    score_sortino9 = rank_score(sortino9)
    score_sortino12 = rank_score(sortino12)

    # -------------------------------------------------
    # 5. 최종 점수
    # -------------------------------------------------
    total_score = (
        WEIGHT_1M_RETURN * score_r1
        + WEIGHT_3M_RETURN * score_r3
        + WEIGHT_6M_RETURN * score_r6
        + WEIGHT_9M_RETURN * score_r9
        + WEIGHT_12M_RETURN * score_r12
        + WEIGHT_6M_SHARPE * score_sharpe6
        + WEIGHT_9M_SHARPE * score_sharpe9
        + WEIGHT_12M_SHARPE * score_sharpe12
        + WEIGHT_9M_SORTINO * score_sortino9
        + WEIGHT_12M_SORTINO * score_sortino12
    )

    # 10개 자산 모두 점수가 존재하는 마지막 월을 신호 기준일로 사용
    complete_rows = total_score.dropna(how="any")

    if complete_rows.empty:
        last_date = total_score.index[-1]
        nan_assets = total_score.loc[last_date][total_score.loc[last_date].isna()].index.tolist()

        raise ValueError(
            "10개 자산 모두에 대해 유효한 점수를 계산할 수 있는 월이 없습니다.\n"
            f"가장 최근 확인 월: {last_date.strftime('%Y-%m-%d')}\n"
            f"점수가 없는 자산: {nan_assets}\n"
            "가능한 원인: 특정 ETF 데이터 누락, 아직 끝나지 않은 월 데이터 혼입, "
            "또는 12개월 지표 계산에 필요한 데이터 부족."
        )

    latest_signal_date = complete_rows.index[-1]
    latest_scores = total_score.loc[latest_signal_date, expected_assets]

    if latest_scores.isna().any():
        na_assets = latest_scores[latest_scores.isna()].index.tolist()
        raise ValueError(f"최신 신호 기준일에 점수가 없는 자산이 있습니다: {na_assets}")

    detail = pd.DataFrame({
        "asset": expected_assets,
        "name": [ASSETS[a]["name"] for a in expected_assets],
        "score_total": latest_scores.values,

        "score_1m_return": score_r1.loc[latest_signal_date, expected_assets].values,
        "score_3m_return": score_r3.loc[latest_signal_date, expected_assets].values,
        "score_6m_return": score_r6.loc[latest_signal_date, expected_assets].values,
        "score_9m_return": score_r9.loc[latest_signal_date, expected_assets].values,
        "score_12m_return": score_r12.loc[latest_signal_date, expected_assets].values,

        "score_6m_sharpe": score_sharpe6.loc[latest_signal_date, expected_assets].values,
        "score_9m_sharpe": score_sharpe9.loc[latest_signal_date, expected_assets].values,
        "score_12m_sharpe": score_sharpe12.loc[latest_signal_date, expected_assets].values,

        "score_9m_sortino": score_sortino9.loc[latest_signal_date, expected_assets].values,
        "score_12m_sortino": score_sortino12.loc[latest_signal_date, expected_assets].values,

        "return_1m": r1.loc[latest_signal_date, expected_assets].values,
        "return_3m": r3.loc[latest_signal_date, expected_assets].values,
        "return_6m": r6.loc[latest_signal_date, expected_assets].values,
        "return_9m": r9.loc[latest_signal_date, expected_assets].values,
        "return_12m": r12.loc[latest_signal_date, expected_assets].values,

        "sharpe_6m": sharpe6.loc[latest_signal_date, expected_assets].values,
        "sharpe_9m": sharpe9.loc[latest_signal_date, expected_assets].values,
        "sharpe_12m": sharpe12.loc[latest_signal_date, expected_assets].values,

        "sortino_9m": sortino9.loc[latest_signal_date, expected_assets].values,
        "sortino_12m": sortino12.loc[latest_signal_date, expected_assets].values,
    })

    detail = detail.sort_values("score_total", ascending=False).reset_index(drop=True)
    detail["rank"] = np.arange(1, len(detail) + 1)

    detail = detail[
        [
            "rank",
            "asset",
            "name",
            "score_total",

            "score_1m_return",
            "score_3m_return",
            "score_6m_return",
            "score_9m_return",
            "score_12m_return",

            "score_6m_sharpe",
            "score_9m_sharpe",
            "score_12m_sharpe",

            "score_9m_sortino",
            "score_12m_sortino",

            "return_1m",
            "return_3m",
            "return_6m",
            "return_9m",
            "return_12m",

            "sharpe_6m",
            "sharpe_9m",
            "sharpe_12m",

            "sortino_9m",
            "sortino_12m",
        ]
    ]

    top_assets = detail.head(TOP_N).set_index("asset")["score_total"]

    return {
        "signal_date": latest_signal_date,
        "top_assets": top_assets,
        "detail": detail,
        "returns": returns,
        "prices_krw": prices_krw,
    }


# =====================================================
# 5. Telegram 알림
# =====================================================

def format_pct(x: float) -> str:
    if pd.isna(x):
        return "N/A"
    return f"{x * 100:.2f}%"


def format_float(x: float) -> str:
    if pd.isna(x):
        return "N/A"
    return f"{x:.2f}"


def build_message(signal: dict) -> str:
    signal_date = signal["signal_date"]
    detail = signal["detail"].copy()

    lines = []
    lines.append("📈 듀얼 모멘텀 월간 신호")
    lines.append("")
    lines.append(f"신호 기준일: {signal_date.strftime('%Y-%m-%d')}")
    lines.append("")
    lines.append("전략 비중:")
    lines.append(f"- 1개월 수익률: {int(WEIGHT_1M_RETURN * 100)}%")
    lines.append(f"- 3개월 수익률: {int(WEIGHT_3M_RETURN * 100)}%")
    lines.append(f"- 6개월 수익률: {int(WEIGHT_6M_RETURN * 100)}%")
    lines.append(f"- 9개월 수익률: {int(WEIGHT_9M_RETURN * 100)}%")
    lines.append(f"- 12개월 수익률: {int(WEIGHT_12M_RETURN * 100)}%")
    lines.append(f"- 6개월 샤프지수: {int(WEIGHT_6M_SHARPE * 100)}%")
    lines.append(f"- 9개월 샤프지수: {int(WEIGHT_9M_SHARPE * 100)}%")
    lines.append(f"- 12개월 샤프지수: {int(WEIGHT_12M_SHARPE * 100)}%")
    lines.append(f"- 9개월 소르티노 지수: {int(WEIGHT_9M_SORTINO * 100)}%")
    lines.append(f"- 12개월 소르티노 지수: {int(WEIGHT_12M_SORTINO * 100)}%")
    lines.append("")
    lines.append("평가 결과 :")
    lines.append("")

    for _, row in detail.iterrows():
        rank = int(row["rank"])
        asset = row["asset"]
        name = row["name"]
        score = row["score_total"]

        lines.append(f"{rank}. {asset} | {name}")
        lines.append(f">> 총점 : {score:.2f}")
        lines.append(f"* 1M : {format_pct(row['return_1m'])}")
        lines.append(f"* 3M : {format_pct(row['return_3m'])}")
        lines.append(f"* 6M : {format_pct(row['return_6m'])}")
        lines.append(f"* 9M : {format_pct(row['return_9m'])}")
        lines.append(f"* 12M : {format_pct(row['return_12m'])}")
        lines.append(f"* Sharpe6M : {format_float(row['sharpe_6m'])}")
        lines.append(f"* Sharpe9M : {format_float(row['sharpe_9m'])}")
        lines.append(f"* Sharpe12M : {format_float(row['sharpe_12m'])}")
        lines.append(f"* Sortino9M : {format_float(row['sortino_9m'])}")
        lines.append(f"* Sortino12M : {format_float(row['sortino_12m'])}")
        lines.append("")

    lines.append("권장 비중: 상위 3개 균등비중")
    lines.append("각 종목 약 33.33%")
    lines.append("")
    lines.append("주의: yfinance 조정가격 기반 자동 산출값입니다. 실제 주문 전 가격·환율·세금·스프레드를 확인하세요.")

    return "\n".join(lines)


def send_telegram_message(message: str):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        raise EnvironmentError(
            "TELEGRAM_BOT_TOKEN 또는 TELEGRAM_CHAT_ID 환경변수가 설정되어 있지 않습니다."
        )

    url = f"https://api.telegram.org/bot{token}/sendMessage"

    payload = {
        "chat_id": chat_id,
        "text": message,
        "disable_web_page_preview": True,
    }

    response = requests.post(url, data=payload, timeout=30)

    if response.status_code != 200:
        raise RuntimeError(f"Telegram 전송 실패: {response.status_code} / {response.text}")


# =====================================================
# 6. 엑셀 저장
# =====================================================

def save_output(signal: dict) -> Path:
    today_str = datetime.now().strftime("%Y%m%d")
    output_file = OUTPUT_DIR / f"dual_momentum_signal_{today_str}.xlsx"

    with pd.ExcelWriter(output_file, engine="openpyxl") as writer:
        signal["detail"].to_excel(writer, sheet_name="Latest_Signal", index=False)
        signal["prices_krw"].to_excel(writer, sheet_name="Monthly_Prices_KRW")
        signal["returns"].to_excel(writer, sheet_name="Monthly_Returns_KRW")

    return output_file


# =====================================================
# 7. 메인 실행
# =====================================================

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--force",
        action="store_true",
        help="두 번째 영업일이 아니어도 강제로 실행합니다.",
    )
    parser.add_argument(
        "--no-send",
        action="store_true",
        help="Telegram 전송 없이 엑셀 파일만 생성합니다.",
    )
    args = parser.parse_args()

    today = today_kst()

    if not args.force and not is_second_business_day(today):
        print(f"{today}은 두 번째 영업일이 아니므로 실행하지 않습니다.")
        return

    print("데이터 다운로드 및 신호 계산을 시작합니다.")

    prices_krw, _ = build_monthly_prices_krw()
    signal = calc_latest_signal(prices_krw)

    output_file = save_output(signal)

    message = build_message(signal)

    print(message)
    print(f"\n엑셀 저장 완료: {output_file}")

    if not args.no_send:
        send_telegram_message(message)
        print("Telegram 알림 전송 완료.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        error_message = f"듀얼 모멘텀 알림 프로그램 오류:\n{e}"
        print(error_message, file=sys.stderr)

        # 오류도 Telegram으로 보내고 싶으면 시도
        try:
            send_telegram_message(error_message)
        except Exception:
            pass

        sys.exit(1)
