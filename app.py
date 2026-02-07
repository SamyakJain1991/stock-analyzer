from flask import Flask, request, render_template
import requests
import yfinance as yf
import numpy as np
import pandas as pd
from finta import TA
import os

app = Flask(__name__)

# --- Helper: sanitize ticker ---
def sanitize_ticker(raw_input):
    if raw_input is None:
        return "RELIANCE"
    while isinstance(raw_input, (list, tuple)):
        if len(raw_input) == 0:
            return "RELIANCE"
        raw_input = raw_input[0]
    return str(raw_input).strip().upper().replace(" ", "").replace(",", "")

# --- NSE realtime fetch ---
def fetch_nse_data(symbol):
    url = f"https://www.nseindia.com/api/quote-equity?symbol={symbol}"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
        "Referer": "https://www.nseindia.com/"
    }
    try:
        session = requests.Session()
        session.get("https://www.nseindia.com", headers=headers, timeout=10)
        resp = session.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            return resp.json()
        else:
            return None
    except Exception:
        return None

# --- NSE stock list preload ---
def get_nse_stock_list():
    try:
        df = pd.read_csv("EQUITY_L.csv")
        return df['SYMBOL'].dropna().tolist()
    except Exception:
        return ["SBIN","TCS","INFY","RELIANCE","HDFCBANK"]

STOCK_LIST = get_nse_stock_list()

@app.route('/')
def home():
    return render_template('index.html', analysis=None, stock_list=STOCK_LIST)

# ✅ Naya route yahan add karo
@app.route('/live_price', methods=["GET"])
def live_price():
    raw_input = request.args.get('ticker') or "RELIANCE"
    raw_input = sanitize_ticker(raw_input)

    ticker = yf.Ticker(raw_input + ".NS")
    info = ticker.history(period="1d", interval="1m")

    if info.empty:
        return {"error": f"No live data found for {raw_input}"}

    current_price = round(info['Close'].iloc[-1], 2)

    return {
        "ticker": raw_input,
        "current_price": f"₹{current_price}"
    }

@app.route('/analyze', methods=["GET","POST"])
def analyze():
    raw_input = request.args.get('ticker') or request.form.get('ticker') or request.form.get('search') or "RELIANCE"
    raw_input = sanitize_ticker(raw_input)

    # --- NSE API block ---
    if raw_input in STOCK_LIST:
        nse_data = fetch_nse_data(raw_input)
        if nse_data:
            info = nse_data.get("info", {})
            company_name = info.get("companyName", raw_input)
            sector = info.get("industry", "N/A")
            prices = nse_data.get("priceInfo", {})
            last_price = prices.get("lastPrice", "N/A")
            prev_close = prices.get("previousClose", "N/A")
            current_price = last_price


            score = 0
            if last_price != "N/A" and prev_close != "N/A":
                if last_price > prev_close:
                    score += 1
                elif last_price < prev_close:
                    score -= 1

            # Unified verdicts
            if score >= 3:
                verdict_msg = f"🟢 Strong Buy — High confidence. (Score {score})"
                confidence = "High"
            elif score in [1,2]:
                verdict_msg = f"⚠️ Cautious Buy — Mild bullish. (Score {score})"
                confidence = "Medium"
            elif score <= -3:
                verdict_msg = f"🔴 Strong Sell — High confidence bearish. (Score {score})"
                confidence = "High"
            elif score in [-1,-2]:
                verdict_msg = f"⚠️ Cautious Sell — Mild bearish. (Score {score})"
                confidence = "Medium"
            else:
                verdict_msg = f"⚖️ Neutral — No clear momentum. (Score {score})"
                confidence = "Low"

            analysis = {
                "ticker": raw_input,
                "Company": company_name,
                "Sector": sector,
                "Description": f"📌 {company_name} ka sector {sector} hai.",
                "CurrentPrice": f"💰 Current Price: ₹{current_price}",
                "Trend": f"{verdict_msg} | Confidence: {confidence}",
                "Entry": "🎯 Suggested Entry Zone: Wait for clearer signals.",
                "Exit": f"✅ Exit Strategy: Target exit around ₹{round(last_price*1.03,2)}" if last_price!="N/A" else "N/A",
                "StopLoss": "🛑 Stop-loss: N/A",
                "Verdict": verdict_msg,
                "Disclaimer": "This analysis is for educational purposes only. Not financial advice."
            }
            return render_template('index.html', analysis=analysis, stock_list=STOCK_LIST)

    # --- Yahoo fallback ---
    ticker = raw_input + ".NS"
    data = yf.download(ticker, period='6mo', interval='1d')
    if data.empty:
        ticker = raw_input + ".BO"
        data = yf.download(ticker, period='6mo', interval='1d')
    if data.empty:
        data = yf.download(raw_input, period='6mo', interval='1d')
    if data.empty:
        return render_template('index.html', analysis={'error': f'Sorry, no reliable data found for {raw_input}. Please check the ticker symbol or try another stock.'}, stock_list=STOCK_LIST)

    data = data.dropna()
    data = data.rename(columns={
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Volume": "volume"
    })
    data = data[['open','high','low','close','volume']]

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
    close_price = safe_val(data['close'])
    bb_upper = safe_val(data['BB_upper'])
    bb_lower = safe_val(data['BB_lower'])
    volume_check = data['volume'].iloc[-1] > data['volume'].tail(10).mean()
    avg_volume = round(data['volume'].tail(20).mean(), 2)   # 20‑day average
    latest_volume = safe_val(data['volume'])                # latest volume
    volume_status = "📊 Volume spike detected" if latest_volume > avg_volume else "📉 Volume normal"
    current_price = close_price   # ✅ Current Price = Close Price


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

    if macd_val != "N/A" and macd_val > 0:
        score += 1
        details.append("📈 MACD bullish (+1)")
    elif macd_val != "N/A":
        score -= 1
        details.append("📉 MACD bearish (-1)")

    if close_price != "N/A" and bb_upper != "N/A" and bb_lower != "N/A":
        if close_price > bb_upper:
            score -= 1
            details.append("📉 Price above Bollinger upper band (overbought)")
        elif close_price < bb_lower:
            score += 1
            details.append("📈 Price below Bollinger lower band (oversold)")

    if volume_check:
        score += 1
        details.append("📊 Volume spike (+1)")

    # Final verdict
       
    if score >= 3:
        verdict_msg = f"🟢 Strong Buy — All indicators aligned bullish. High-confidence buying opportunity! (Score {score})"
        entry_zone = f"₹{round(close_price*0.97,2)} – ₹{round(close_price*0.99,2)}"
        stop_loss = f"₹{round(close_price*0.95,2)}"
    elif score <= -3:
        verdict_msg = f"🔴 Strong Sell — Indicators show bearish momentum. Avoid buying, shorting may be considered. (Score {score})"
        entry_zone = f"Sell near ₹{close_price}, target lower levels."
        stop_loss = f"₹{round(close_price*1.02,2)}"
    elif -2 <= score <= 2:
        verdict_msg = f"⚖️ Neutral — Signals are mixed. Best to wait for confirmation. (Score {score})"
        entry_zone = "Wait for clearer signals before entry."
        stop_loss = "N/A"
    else:
        verdict_msg = f"❓ Mixed — Indicators conflict. Trade cautiously. (Score {score})"
        entry_zone = "No clear entry zone."
        stop_loss = "N/A"

    analysis = {
    "ticker": raw_input,
    "Company": ticker,
    "Sector": "N/A",
    "Description": f"📌 {ticker} ka sector data unavailable hai.",
    "CurrentPrice": f"💰 Current Price: ₹{current_price}", 
    "Indicators": details,
    "Volume": f"Latest: {latest_volume}, Avg(20d): {avg_volume} → {volume_status}",   # ✅ Add here
    "Score": score,
    "Verdict": verdict_msg,
    "Entry": f"🎯 Suggested Entry Zone: {entry_zone}",
    "Exit": f"✅ Target Exit: ₹{round(close_price*1.03,2)}"  if close_price!="N/A" else "N/A",
    "StopLoss": f"🛑 Stop-loss: ₹{round(close_price*0.98,2)}" if close_price!="N/A" else "N/A"
    }

    return render_template('index.html', analysis=analysis)

# ✅ Render ke liye mandatory block
if __name__ == "__main__":
    port = int(os.  environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)