from flask import Flask, request, render_template
import requests
import yfinance as yf
import numpy as np
import pandas as pd
from finta import TA
import os
import time

app = Flask(__name__)


def build_trade_plan(verdict_msg, score, current_price, stop_loss, target_price):
    risk_note = "Capital at risk per trade should generally stay below 1-2%."
    if "Strong Buy" in verdict_msg:
        action = "Bias: Long"
        checklist = [
            "Wait for confirmation candle near support / entry zone.",
            "Enter in parts instead of full quantity at once.",
            "Trail stop-loss after target-1 is reached."
        ]
    elif "Strong Sell" in verdict_msg:
        action = "Bias: Defensive / Short setups only"
        checklist = [
            "Avoid fresh long positions until trend improves.",
            "For short setups, wait for pullback rejection.",
            "Keep strict stop-loss due to sharp reversals."
        ]
    else:
        action = "Bias: Wait & Watch"
        checklist = [
            "No aggressive entry until multiple signals align.",
            "Track breakout above resistance or breakdown below support.",
            "Preserve capital during low-conviction setups."
        ]

    return {
        "Action": action,
        "ScoreLabel": f"Composite Technical Score: {score}",
        "CurrentPriceValue": current_price,
        "StopLossValue": stop_loss,
        "TargetValue": target_price,
        "RiskNote": risk_note,
        "Checklist": checklist,
    }

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

# ✅ NEW: Retry function to handle rate limits
def fetch_data_with_retry(ticker, max_retries=3):
    """Fetch data with retry mechanism and delays"""
    for attempt in range(max_retries):
        try:
            print(f"Attempt {attempt + 1}: Downloading {ticker}...")
            data = yf.download(ticker, period='6mo', interval='1d', progress=False)
            
            if not data.empty:
                print(f"✅ Successfully downloaded {ticker}")
                return data
            else:
                print(f"⚠️ {ticker} returned empty data")
        except Exception as e:
            print(f"❌ Error downloading {ticker}: {e}")
        
        # Wait before retry (avoid rate limiting)
        if attempt < max_retries - 1:
            wait_time = 2 ** attempt  # Exponential backoff: 1, 2, 4 seconds
            print(f"Waiting {wait_time} seconds before retry...")
            time.sleep(wait_time)
    
    return pd.DataFrame()  # Return empty DataFrame if all retries fail

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
            day_high = prices.get("intraDayHighLow", {}).get("max", "N/A")
            day_low = prices.get("intraDayHighLow", {}).get("min", "N/A")
            day_range = f"📊 Day Range: ₹{day_low} - ₹{day_high}"

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

            stop_loss_value = round(last_price * 0.98, 2) if last_price != "N/A" else "N/A"
            target_value = round(last_price * 1.03, 2) if last_price != "N/A" else "N/A"
            trade_plan = build_trade_plan(
                verdict_msg,
                score,
                last_price,
                stop_loss_value,
                target_value,
            )

            analysis = {
                "ticker": raw_input,
                "Company": company_name,
                "Sector": sector,
                "Description": f"📌 {company_name} ka sector {sector} hai.",
                "CurrentPrice": f"💰 Current Price: ₹{current_price}",
                "DayRange": day_range,
                "Trend": f"{verdict_msg} | Confidence: {confidence}",
                "Entry": "🎯 Suggested Entry Zone: Wait for clearer signals.",
                "Exit": f"✅ Exit Strategy: Target exit around ₹{target_value}" if last_price!="N/A" else "N/A",
                "StopLoss": f"🛑 Stop-loss: ₹{stop_loss_value}" if last_price!="N/A" else "N/A",
                "Verdict": verdict_msg,
                "Disclaimer": "This analysis is for educational purposes only. Not financial advice.",
                "Score": score,
                "TradePlan": trade_plan,
            }
            return render_template('index.html', analysis=analysis, stock_list=STOCK_LIST)

    # --- Yahoo fallback with retry mechanism ---
    # ✅ FIXED: Try without .NS first (since it was working before)
    data = fetch_data_with_retry(raw_input)
    
    if data.empty:
        # Try with .NS suffix
        data = fetch_data_with_retry(raw_input + ".NS")
    
    if data.empty:
        # Try with .BO suffix (BSE)
        data = fetch_data_with_retry(raw_input + ".BO")
    
    if data.empty:
        return render_template('index.html', analysis={'error': f'Sorry, no reliable data found for {raw_input}. Please check the ticker symbol or try another stock. The service may also be rate-limited by Yahoo Finance.'}, stock_list=STOCK_LIST)

    data = data.dropna()
    data = data.rename(columns={
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Volume": "volume"
    })
    data = data[['open','high','low','close','volume']]

    def safe_val(series, default=None):
        """Returns numeric value or None (not "N/A" string)"""
        try:
            val = series.iloc[-1]
            if pd.isna(val):
                return default
            return round(float(val), 2)
        except Exception:
            return default

    # ✅ FIXED: Properly extract indicator values from finta
    try:
        sma10_result = TA.SMA(data, 10)
        data['SMA_10'] = sma10_result if isinstance(sma10_result, pd.Series) else sma10_result.iloc[:, 0]
    except Exception as e:
        print(f"SMA_10 error: {e}")
        data['SMA_10'] = np.nan

    try:
        sma30_result = TA.SMA(data, 30)
        data['SMA_30'] = sma30_result if isinstance(sma30_result, pd.Series) else sma30_result.iloc[:, 0]
    except Exception as e:
        print(f"SMA_30 error: {e}")
        data['SMA_30'] = np.nan

    try:
        ema20_result = TA.EMA(data, 20)
        data['EMA_20'] = ema20_result if isinstance(ema20_result, pd.Series) else ema20_result.iloc[:, 0]
    except Exception as e:
        print(f"EMA_20 error: {e}")
        data['EMA_20'] = np.nan

    try:
        rsi_result = TA.RSI(data)
        data['RSI'] = rsi_result if isinstance(rsi_result, pd.Series) else rsi_result.iloc[:, 0]
    except Exception as e:
        print(f"RSI error: {e}")
        data['RSI'] = np.nan

    try:
        macd_result = TA.MACD(data)
        if isinstance(macd_result, pd.DataFrame):
            data['MACD'] = macd_result['MACD']
        else:
            data['MACD'] = macd_result
    except Exception as e:
        print(f"MACD error: {e}")
        data['MACD'] = np.nan

    try:
        bb_result = TA.BBANDS(data)
        if isinstance(bb_result, pd.DataFrame):
            data['BB_upper'] = bb_result['BB_UPPER']
            data['BB_lower'] = bb_result['BB_LOWER']
        else:
            data['BB_upper'] = np.nan
            data['BB_lower'] = np.nan
    except Exception as e:
        print(f"BBANDS error: {e}")
        data['BB_upper'] = np.nan
        data['BB_lower'] = np.nan

    # ✅ FIXED: Get numeric values (None if unavailable, not "N/A" strings)
    sma10 = safe_val(data['SMA_10'])
    sma30 = safe_val(data['SMA_30'])
    ema20 = safe_val(data['EMA_20'])
    rsi_val = safe_val(data['RSI'])
    macd_val = safe_val(data['MACD'])
    close_price = safe_val(data['close'])
    bb_upper = safe_val(data['BB_upper'])
    bb_lower = safe_val(data['BB_lower'])
    
    # ✅ FIXED: Volume handling - use .iloc[-1] to get scalar boolean
    try:
        latest_volume_val = data['volume'].iloc[-1]
        avg_10_volume = data['volume'].tail(10).mean()
        volume_check = bool(latest_volume_val > avg_10_volume)  # ✅ Convert to boolean
        
        avg_volume = round(data['volume'].tail(20).mean(), 2)
        latest_volume = safe_val(data['volume'])
        if latest_volume is not None and avg_volume is not None:
            volume_status = "📊 Volume spike detected" if latest_volume > avg_volume else "📉 Volume normal"
        else:
            volume_status = "📉 Volume data unavailable"
    except Exception as e:
        print(f"Volume error: {e}")
        volume_check = False
        avg_volume = None
        latest_volume = None
        volume_status = "📉 Volume data unavailable"
    
    current_price = close_price if close_price is not None else 0

    # Scoring
    score = 0
    details = []

    if sma10 is not None and sma30 is not None and sma10 > sma30:
        score += 1
        details.append("📈 SMA crossover bullish (+1)")
    else:
        score -= 1
        details.append("📉 SMA crossover bearish (-1)")

    if ema20 is not None and close_price is not None and close_price > ema20:
        score += 1
        details.append("📈 Price above EMA20 (+1)")
    else:
        score -= 1
        details.append("📉 Price below EMA20 (-1)")

    if rsi_val is not None:
        if rsi_val > 55:
            score += 1
            details.append(f"💪 RSI {rsi_val} bullish (+1)")
        elif rsi_val < 45:
            score -= 1
            details.append(f"😓 RSI {rsi_val} bearish (-1)")

    if macd_val is not None and macd_val > 0:
        score += 1
        details.append("📈 MACD bullish (+1)")
    elif macd_val is not None:
        score -= 1
        details.append("📉 MACD bearish (-1)")

    if close_price is not None and bb_upper is not None and bb_lower is not None:
        if close_price > bb_upper:
            score -= 1
            details.append("📉 Price above Bollinger upper band (overbought)")
        elif close_price < bb_lower:
            score += 1
            details.append("📈 Price below Bollinger lower band (oversold)")

    if volume_check:  # ✅ Now this is a safe boolean
        score += 1
        details.append("📊 Volume spike (+1)")

    # Final verdict
    if score >= 3:
        verdict_msg = f"🟢 Strong Buy — All indicators aligned bullish. High-confidence buying opportunity! (Score {score})"
        entry_zone = f"₹{round(close_price*0.97,2)} – ₹{round(close_price*0.99,2)}" if close_price else "N/A"
        stop_loss = f"₹{round(close_price*0.95,2)}" if close_price else "N/A"
    elif score <= -3:
        verdict_msg = f"🔴 Strong Sell — Indicators show bearish momentum. Avoid buying, shorting may be considered. (Score {score})"
        entry_zone = f"Sell near ₹{close_price}, target lower levels." if close_price else "N/A"
        stop_loss = f"₹{round(close_price*1.02,2)}" if close_price else "N/A"
    elif -2 <= score <= 2:
        verdict_msg = f"⚖️ Neutral — Signals are mixed. Best to wait for confirmation. (Score {score})"
        entry_zone = "Wait for clearer signals before entry."
        stop_loss = "N/A"
    else:
        verdict_msg = f"❓ Mixed — Indicators conflict. Trade cautiously. (Score {score})"
        entry_zone = "No clear entry zone."
        stop_loss = "N/A"

    stop_loss_value = round(close_price * 0.98, 2) if close_price else "N/A"
    target_value = round(close_price * 1.03, 2) if close_price else "N/A"
    trade_plan = build_trade_plan(
        verdict_msg,
        score,
        close_price if close_price else "N/A",
        stop_loss_value,
        target_value,
    )

    # ✅ FIXED: Proper volume display
    volume_display = f"Latest: {latest_volume}, Avg(20d): {avg_volume} → {volume_status}" if latest_volume is not None else "Volume data unavailable"

    analysis = {
        "ticker": raw_input,
        "Company": raw_input,
        "Sector": "N/A",
        "Description": f"📌 {raw_input} Technical Analysis",
        "CurrentPrice": f"💰 Current Price: ₹{current_price}" if current_price else "N/A",
        "Indicators": details,
        "Volume": volume_display,
        "Score": score,
        "Verdict": verdict_msg,
        "Entry": f"🎯 Suggested Entry Zone: {entry_zone}",
        "Exit": f"✅ Target Exit: ₹{target_value}" if close_price else "N/A",
        "StopLoss": f"🛑 Stop-loss: ₹{stop_loss_value}" if close_price else "N/A",
        "TradePlan": trade_plan,
        "Disclaimer": "This analysis is for educational purposes only. Not financial advice."
    }

    return render_template('index.html', analysis=analysis, stock_list=STOCK_LIST)

# ✅ Render ke liye mandatory block
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
