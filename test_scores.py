import yfinance as yf
import numpy as np
from finta import TA

# --- Helper: safe value extraction ---
def safe_val(series, default="N/A"):
    try:
        val = series.iloc[-1]
        if np.isnan(val):
            return default
        return round(val, 2)
    except Exception:
        return default

# --- Scoring function (same as your app.py logic) ---
def analyze_stock(ticker):
    data = yf.download(ticker, period='6mo', interval='1d')
    if data.empty:
        return {"ticker": ticker, "score": "No data"}
    data = data.dropna()

    # Indicators (corrected syntax for finta)
    data['SMA_10'] = TA.SMA(data, period=10)
    data['SMA_30'] = TA.SMA(data, period=30)
    data['EMA_20'] = TA.EMA(data, period=20)
    data['RSI'] = TA.RSI(data, period=14)
    macd = TA.MACD(data)
    data['MACD'] = macd['MACD']
    bb = TA.BBANDS(data)
    data['BB_upper'] = bb['BB_UPPER']
    data['BB_lower'] = bb['BB_LOWER']

    # Values
    sma10 = safe_val(data['SMA_10'])
    sma30 = safe_val(data['SMA_30'])
    ema20 = safe_val(data['EMA_20'])
    rsi_val = safe_val(data['RSI'])
    macd_val = safe_val(data['MACD'])
    close_price = safe_val(data['Close'])
    bb_upper = safe_val(data['BB_upper'])
    bb_lower = safe_val(data['BB_lower'])
    volume_check = data['Volume'].iloc[-1] > data['Volume'].tail(10).mean()

    # Scoring
    score = 0
    details = []

    if sma10 != "N/A" and sma30 != "N/A" and sma10 > sma30:
        score += 1
        details.append("📈 SMA crossover bullish (+1)")
    else:
        score -= 1
        details.append("📉 SMA crossover bearish (-1)")

    if ema20 != "N/A" and close_price != "N/A" and close_price > ema20:
        score += 1
        details.append("📈 Price above EMA20 (+1)")
    else:
        score -= 1
        details.append("📉 Price below EMA20 (-1)")

    if rsi_val != "N/A":
        if rsi_val > 55:
            score += 1
            details.append(f"💪 RSI {rsi_val} bullish (+1)")
        elif rsi_val < 45:
            score -= 1
            details.append(f"😓 RSI {rsi_val} bearish (-1)")

    if macd_val != "N/A":
        if macd_val > 0:
            score += 1
            details.append(f"📊 MACD {macd_val} positive (+1)")
        else:
            score -= 1
            details.append(f"📊 MACD {macd_val} negative (-1)")

    if bb_upper != "N/A" and bb_lower != "N/A" and close_price != "N/A":
        if close_price < bb_lower:
            score += 1
            details.append("📉 Near lower Bollinger Band rebound (+1)")
        elif close_price > bb_upper:
            score -= 1
            details.append("📈 Near upper Bollinger Band overbought (-1)")

    if volume_check:
        score += 1
        details.append("🔊 Volume spike (+1)")

    return {"ticker": ticker, "score": score, "details": details}

# --- Test tickers ---
tickers = [
    "SBIN.NS", "TCS.NS", "INFY.NS", "RELIANCE.NS",
    "HDFCBANK.NS", "ICICIBANK.NS", "NATIONALUM.NS",
    "HINDCOPPER.NS", "IDEA.NS", "YESBANK.NS"
]

# --- Run analysis ---
for t in tickers:
    result = analyze_stock(t)
    print(f"{result['ticker']} → Score: {result['score']}")
    for d in result['details']:
        print("   ", d)
    print("-"*50)