from flask import Flask, request, render_template
import requests
import yfinance as yf
import numpy as np
from finta import TA
import os

app = Flask(__name__)

def sanitize_ticker(raw_input):
    if raw_input is None:
        return "RELIANCE"
    while isinstance(raw_input, (list, tuple)):
        if len(raw_input) == 0:
            return "RELIANCE"
        raw_input = raw_input[0]
    return str(raw_input).strip().upper().replace(" ", "").replace(",", "")

def fetch_nse_data(symbol):
    url = f"https://www.nseindia.com/api/quote-equity?symbol={symbol}"
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    try:
        session = requests.Session()
        resp = session.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            return resp.json()
        else:
            return None
    except Exception:
        return None

@app.route('/')
def home():
    return render_template('index.html', analysis=None)

@app.route('/analyze')
def analyze():
    raw_input = request.args.get('ticker', default='RELIANCE')
    raw_input = sanitize_ticker(raw_input)

    # --- NSE API ---
    nse_data = fetch_nse_data(raw_input)
    if nse_data:
        info = nse_data.get("info", {})
        company_name = info.get("companyName", raw_input)
        sector = info.get("industry", "N/A")
        prices = nse_data.get("priceInfo", {})
        last_price = prices.get("lastPrice", "N/A")
        prev_close = prices.get("previousClose", "N/A")

        verdict_status = "Bullish" if last_price != "N/A" and prev_close != "N/A" and last_price > prev_close else "Bearish"

        analysis = {
            "ticker": raw_input,
            "Company": company_name,
            "Sector": sector,
            "Description": f"{company_name} ka sector {sector} hai.",
            "Trend": f"Trend Analysis: Stock abhi {verdict_status} lag raha hai (NSE data ke hisaab se).",
            "Entry": f"Entry Strategy: Current price {last_price}.",
            "SuggestedEntry": f"Suggested Entry Price: {last_price} (basic NSE calculation)",
            "Exit": f"Exit Strategy: Target exit around {round(last_price*1.03,2)}" if last_price!="N/A" else "N/A",
            "StopLoss": f"Stop-loss Strategy: Stop-loss {round(last_price*0.98,2)}" if last_price!="N/A" else "N/A",
            "Verdict": f"Final Verdict: Stock is {verdict_status}. Trade cautiously — NSE data limited."
        }
        return render_template('index.html', analysis=analysis)

    # --- Yahoo Finance fallback ---
    ticker = raw_input
    if not ticker.endswith(".NSE") and not ticker.endswith(".NS") and not ticker.endswith(".BO"):
        ticker = ticker + ".NS"

    try:
        data = yf.download(ticker, period='6mo', interval='1d')
    except Exception as e:
        return render_template('index.html', analysis={'error': f'Yahoo Finance error: {str(e)}'})

    if data.empty:
        return render_template('index.html', analysis={'error': f'No data found for {ticker}'})
    data = data.dropna()

    def safe_val(series, default="N/A"):
        try:
            val = series.iloc[-1]
            if np.isnan(val):
                return default
            return round(val, 2)
        except Exception:
            return default

    # Indicators
    data['SMA_10'] = TA.SMA(data, 10)
    data['SMA_30'] = TA.SMA(data, 30)
    data['EMA_20'] = TA.EMA(data, 20)
    data['RSI'] = TA.RSI(data)
    macd_line = TA.MACD(data)['MACD']
    data['MACD'] = macd_line
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

    # Scoring system
    score = 0
    details = []

    if sma10 != "N/A" and sma30 != "N/A" and sma10 > sma30:
        score += 1
        details.append("SMA10 > SMA30 → Uptrend (+1)")
    else:
        score -= 1
        details.append("SMA10 < SMA30 → Downtrend (-1)")

    if ema20 != "N/A" and close_price != "N/A" and close_price > ema20:
        score += 1
        details.append("Price > EMA20 → Bullish (+1)")
    else:
        score -= 1
        details.append("Price < EMA20 → Bearish (-1)")

    if rsi_val != "N/A":
        if rsi_val > 55:
            score += 1
            details.append(f"RSI {rsi_val} → Bullish momentum (+1)")
        elif rsi_val < 45:
            score -= 1
            details.append(f"RSI {rsi_val} → Bearish momentum (-1)")
        else:
            details.append(f"RSI {rsi_val} → Neutral (0)")

    if macd_val != "N/A":
        if macd_val > 0:
            score += 1
            details.append(f"MACD {macd_val} → Positive crossover (+1)")
        else:
            score -= 1
            details.append(f"MACD {macd_val} → Negative crossover (-1)")

    if bb_upper != "N/A" and bb_lower != "N/A" and close_price != "N/A":
        if close_price < bb_lower:
            score += 1
            details.append("Price near lower Bollinger Band → Potential rebound (+1)")
        elif close_price > bb_upper:
            score -= 1
            details.append("Price near upper Bollinger Band → Overbought (-1)")

    if volume_check:
        score += 1
        details.append("Volume > 10-day average → Strong participation (+1)")

    # Final verdict
    if score >= 3:
        verdict = "Strong Buy"
    elif score <= -3:
        verdict = "Strong Sell"
    elif -2 <= score <= 2:
        verdict = "Neutral / Wait"
    else:
        verdict = "Mixed"

    analysis = {
        "ticker": raw_input,
        "Company": ticker,
        "Sector": "N/A",
        "Description": f"{ticker} ka sector data unavailable hai.",
        "Indicators": details,
        "Score": score,
        "Verdict": f"Final Verdict: {verdict} (Score {score})",
        "Entry": f"Suggested Entry Zone: {round(close_price*0.99,2)} – {close_price}" if close_price!="N/A" else "N/A",
        "Exit": f"Target Exit: {round(close_price*1.03,2)}" if close_price!="N/A" else "N/A",
        "StopLoss": f"Stop-loss: {round(close_price*0.98,2)}" if close_price!="N/A" else "N/A"
    }

    return render_template('index.html', analysis=analysis)


# ✅ Render ke liye mandatory block
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)