from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from datetime import datetime
from dateutil.relativedelta import relativedelta
import yfinance as yf

app = FastAPI(title="Stock & Mutual Fund Analyzer")

# ---------------- UI ROUTE ----------------
@app.get("/", response_class=HTMLResponse)
def home():
    with open("index.html", "r", encoding="utf-8") as f:
        return f.read()

# ---------------- DATA FETCH ----------------
def get_prices(symbol, start, end):
    data = yf.download(
        symbol,
        start=start.strftime("%Y-%m-%d"),
        end=end.strftime("%Y-%m-%d"),
        auto_adjust=True,
        progress=False
    )

    if data is None or data.empty:
        return None, None

    close = data["Close"]

    # Force 1D series (handles yfinance edge cases)
    if hasattr(close.iloc[0], "__iter__"):
        close = close.iloc[:, 0]

    return float(close.iloc[0]), float(close.iloc[-1])

# ---------------- API ----------------
@app.get("/analyze")
def analyze(
    symbol: str,
    duration_value: int,
    duration_unit: str,
    cycles: int,
    end_date: str,
    asset_type: str = "stock"   # stock | mf
):
    if duration_unit not in ["days", "months", "years"]:
        raise HTTPException(status_code=400, detail="Invalid duration_unit")

    # Robust date parsing
    try:
        if "/" in end_date:
            end_date = datetime.strptime(end_date, "%m/%d/%Y")
        else:
            end_date = datetime.strptime(end_date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format")

    results = []
    total_growth = 0
    valid = 0

    # IMPORTANT: correct time anchoring
    oldest_start_price = None   # earliest price
    newest_end_price = None     # latest price

    for i in range(cycles):
        cycle_end = end_date - relativedelta(**{duration_unit: i * duration_value})
        cycle_start = cycle_end - relativedelta(**{duration_unit: duration_value})

        start_price, end_price = get_prices(symbol, cycle_start, cycle_end)
        if start_price is None or end_price is None:
            continue

        # Because we iterate from newest → oldest:
        # overwrite oldest_start_price every time
        oldest_start_price = start_price

        # newest_end_price should only be set once (first valid cycle)
        if newest_end_price is None:
            newest_end_price = end_price

        growth = ((end_price - start_price) / start_price) * 100

        results.append({
            "cycle": i + 1,
            "from": cycle_start.date().isoformat(),
            "to": cycle_end.date().isoformat(),
            "growth_percent": round(growth, 2)
        })

        total_growth += growth
        valid += 1

    if valid == 0:
        raise HTTPException(status_code=404, detail="No data found")

    response = {
        "symbol": symbol.upper(),
        "average_growth_percent": round(total_growth / valid, 2),
        "results": results
    }

    # -------- CAGR ONLY FOR MUTUAL FUNDS (FIXED) --------
    if asset_type == "mf" and oldest_start_price and newest_end_price:
        total_years = duration_value * valid
        if total_years > 0:
            cagr = (newest_end_price / oldest_start_price) ** (1 / total_years) - 1
            response["cagr_percent"] = round(cagr * 100, 2)

    return response
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("stock_cycle_analysis:app", host="0.0.0.0", port=8000)
