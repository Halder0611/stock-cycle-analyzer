from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from datetime import datetime
from dateutil.relativedelta import relativedelta
import statistics
import yfinance as yf

app = FastAPI(title="Stock & Mutual Fund Cycle Analyzer")


# -------------------- UTILS --------------------

def parse_date(d: str) -> datetime:
    try:
        return datetime.strptime(d, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid date format. Use YYYY-MM-DD"
        )


def get_price_series(symbol: str, start: datetime, end: datetime):
    data = yf.download(
        symbol,
        start=start.strftime("%Y-%m-%d"),
        end=end.strftime("%Y-%m-%d"),
        auto_adjust=True,
        progress=False
    )

    if data is None or data.empty:
        raise HTTPException(status_code=404, detail="No price data found")

    close = data["Close"]

    # Handle weird yfinance multi-column edge case
    if hasattr(close.iloc[0], "__iter__"):
        close = close.iloc[:, 0]

    dates = [d.strftime("%Y-%m-%d") for d in close.index]
    prices = [float(p) for p in close.values]

    return dates, prices


# -------------------- HOME --------------------

@app.get("/", response_class=HTMLResponse)
def home():
    with open("index.html", "r", encoding="utf-8") as f:
        return f.read()


# -------------------- ANALYZE --------------------

@app.get("/analyze")
def analyze(
    symbol: str,
    duration_value: int,
    duration_unit: str,
    cycles: int,
    end_date: str,
    asset_type: str = "stock",
    risk_free_rate: float = 0.0   # USER-DEFINED HURDLE RATE (%)
):
    if duration_unit not in ["days", "months", "years"]:
        raise HTTPException(status_code=400, detail="Invalid duration_unit")

    end_date = parse_date(end_date)

    results = []
    cycle_returns = []

    oldest_start_price = None
    newest_end_price = None

    for i in range(cycles):
        cycle_end = end_date - relativedelta(
            **{duration_unit: i * duration_value}
        )
        cycle_start = cycle_end - relativedelta(
            **{duration_unit: duration_value}
        )

        _, prices = get_price_series(symbol, cycle_start, cycle_end)

        start_price = prices[0]
        end_price = prices[-1]

        if oldest_start_price is None:
            oldest_start_price = start_price

        newest_end_price = end_price

        growth = ((end_price - start_price) / start_price) * 100
        cycle_returns.append(growth)

        results.append({
            "cycle": i + 1,
            "from": cycle_start.strftime("%Y-%m-%d"),
            "to": cycle_end.strftime("%Y-%m-%d"),
            "growth_percent": round(growth, 2)
        })

    # -------------------- METRICS --------------------

    avg_return = sum(cycle_returns) / len(cycle_returns)

    std_dev = (
        statistics.pstdev(cycle_returns)
        if len(cycle_returns) > 1
        else 0.0
    )

    # Subjective / hurdle-based Sharpe
    sharpe = (
        (avg_return - risk_free_rate) / std_dev
        if std_dev != 0
        else 0.0
    )

    response = {
        "symbol": symbol.upper(),
        "average_growth_percent": round(avg_return, 2),
        "std_dev_percent": round(std_dev, 2),
        "sharpe_ratio": round(sharpe, 3),
        "risk_free_rate_used": risk_free_rate,
        "results": results
    }

    # CAGR only for mutual funds
    if asset_type == "mf":
        total_years = duration_value * cycles
        cagr = (newest_end_price / oldest_start_price) ** (1 / total_years) - 1
        response["cagr_percent"] = round(cagr * 100, 2)

    return response


# -------------------- PRICE SERIES (GRAPH) --------------------

@app.get("/price-series")
def price_series(
    symbol: str,
    duration_value: int,
    duration_unit: str,
    cycles: int,
    end_date: str
):
    if duration_unit not in ["days", "months", "years"]:
        raise HTTPException(status_code=400, detail="Invalid duration_unit")

    end_date = parse_date(end_date)

    earliest_start = end_date - relativedelta(
        **{duration_unit: duration_value * cycles}
    )

    dates, prices = get_price_series(symbol, earliest_start, end_date)

    cycle_points = []

    for i in range(cycles):
        cycle_end = end_date - relativedelta(
            **{duration_unit: i * duration_value}
        )
        cycle_start = cycle_end - relativedelta(
            **{duration_unit: duration_value}
        )

        cycle_points.append({
            "cycle": i + 1,
            "start": cycle_start.strftime("%Y-%m-%d"),
            "end": cycle_end.strftime("%Y-%m-%d")
        })

    return {
        "symbol": symbol.upper(),
        "dates": dates,
        "prices": prices,
        "cycles": cycle_points
    }
