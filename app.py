from flask import Flask, request, render_template
import requests
import yfinance as yf
import numpy as np
from finta import TA
import os

app = Flask(__name__)

# --- Universal sanitizer for ticker input ---
def sanitize_ticker(raw_input):
    if raw_input is None:
        return "RELIANCE"
    while isinstance(raw_input, (list, tuple)):
        if len(raw_input) == 0:
            return "RELIANCE"
        raw_input = raw_input[0]
    return str(raw_input).strip().upper().replace(" ", "").replace(",", "")

# --- NSE India API fetch ---
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
    try:
        raw_input = request.args.get('ticker', default='RELIANCE')
        raw_input = sanitize_ticker(raw_input)

        # --- Try NSE API first ---
        nse_data = fetch_nse_data(raw_input)
        if nse_data:
            info = nse_data.get("info", {})
            company_name = info.get("companyName", raw_input)
            sector = info.get("industry", "N/A")
            prices = nse_data.get("priceInfo", {})
            last_price = prices.get("lastPrice", "N/A")
            prev_close = prices.get("previousClose", "N/A")

            try:
                # Percentage based ranges
                entry_zone = f"{round(last_price * 0.99, 2)} – {last_price}" if last_price != "N/A" else "N/A"
                invalidation = f"{round(last_price * 0.98, 2)}" if last_price != "N/A" else "N/A"
                exit_target = f"{round(last_price * 1.03, 2)}" if last_price != "N/A" else "N/A"
                stop_loss = f"{round(last_price * 0.98, 2)}" if last_price != "N/A" else "N/A"
            except Exception:
                entry_zone, invalidation, exit_target, stop_loss = "N/A","N/A","N/A","N/A"

            # Simple bullish/bearish guess using last vs previous close
            if last_price != "N/A" and prev_close != "N/A":
                verdict_status = "Bullish" if last_price > prev_close else "Bearish"
            else:
                verdict_status = "Unclear"

            suggested_entry = f"Suggested Entry Price: {entry_zone} (basic NSE calculation)"

            analysis = {
                "ticker": raw_input,
                "Company": company_name,
                "Sector": sector,
                "Description": f"{company_name} ka sector {sector} hai.",
                "Trend": f"Trend Analysis: Stock abhi {verdict_status} lag raha hai (NSE data ke hisaab se).",
                "Entry": f"Entry Strategy: Current price {last_price}. Zone {entry_zone}. Agar price {invalidation} ke neeche girta hai, to analysis fail ho jaayega.",
                "SuggestedEntry": suggested_entry,
                "Exit": f"Exit Strategy: Target exit around {exit_target}.",
                "StopLoss": f"Stop-Loss Strategy: Stop-loss {stop_loss} rakho.",
                "Verdict": f"Final Verdict: Stock is {verdict_status}. Trade cautiously — NSE data limited."
            }
            return render_template('index.html', analysis=analysis)

        # --- Fallback to Yahoo Finance ---
        ticker = raw_input
        if not ticker.endswith(".NSE") and not ticker.endswith(".NS") and not ticker.endswith(".BO"):
            ticker = ticker + ".NS"
        ticker = str(ticker)

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

        # Trend Analysis
        data['SMA_10'] = TA.SMA(data, 10)
        data['SMA_30'] = TA.SMA(data, 30)
        sma10 = safe_val(data['SMA_10'])
        sma30 = safe_val(data['SMA_30'])
        trend = "UP" if sma10 != "N/A" and sma30 != "N/A" and sma10 > sma30 else "DOWN"
        trend_msg = f"Trend Analysis: Stock abhi {'uptrend' if trend=='UP' else 'downtrend'} me hai."

        # Entry Strategy
        data['RSI'] = TA.RSI(data)
        data['MACD'] = TA.MACD(data)['MACD']
        entry_price = safe_val(data['Close'])
        entry_range = f"{round(entry_price * 0.99, 2)} – {entry_price}" if entry_price != "N/A" else "N/A"
        invalidation_level = f"{round(entry_price * 0.98, 2)}" if entry_price != "N/A" else "N/A"
        entry_msg = (
            f"Entry Strategy: RSI {safe_val(data['RSI'])}, MACD {safe_val(data['MACD'])}. "
            f"Zone {entry_range}. Agar price {invalidation_level} ke neeche girta hai, to analysis fail ho jaayega."
        )

        # Suggested Entry Price logic
        rsi_val = safe_val(data['RSI'])
        macd_val = safe_val(data['MACD'])
        volume_check = data['Volume'].iloc[-1] > data['Volume'].tail(10).mean()

        if trend == "UP" and rsi_val != "N/A" and rsi_val > 55 and macd_val != "N/A" and macd_val > 0 and volume_check:
            suggested_entry = f"Suggested Entry Price: {round(entry_price * 0.99, 2)} – {entry_price} (near support zone)"
        elif trend == "DOWN" and rsi_val != "N/A" and rsi_val < 45 and macd_val != "N/A" and macd_val < 0:
            suggested_entry = f"Suggested Entry Price: {round(entry_price * 1.01, 2)}+ (shorting opportunity)"
        elif rsi_val != "N/A" and 45 <= rsi_val <= 55:
            suggested_entry = "Suggested Entry Price: Wait for confirmation, no clear entry."
        else:
            suggested_entry = "Suggested Entry Price: Signals mixed, trade cautiously."

        # Exit Strategy
        exit_msg = f"Exit Strategy: Exit around {round(entry_price * 1.03, 2)}" if entry_price != "N/A" else "Exit Strategy: N/A"

        # Stop-loss Strategy
        stop_loss = f"{round(entry_price * 0.98, 2)}" if entry_price != "N/A" else "N/A"
        stoploss_msg = f"Stop-Loss Strategy: Stop-loss {stop_loss} rakho."

        # --- Enhanced Final Verdict ---
        if trend == "UP" and rsi_val != "N/A" and rsi_val > 55 and macd_val != "N/A" and macd_val > 0 and volume_check:
            verdict_status = "Bullish"
            verdict_msg = f"Final Verdict: Stock is {verdict_status}. Strong Buy Setup — RSI {rsi_val}, MACD {macd_val}, SMA crossover confirmed, volume above average."
        elif trend == "DOWN" and rsi_val != "N/A" and rsi_val < 45 and macd_val != "N/A" and macd_val < 0:
            verdict_status = "Bearish"
            verdict_msg = f"Final Verdict: Stock is {verdict_status}. Strong Sell Setup — RSI {rsi_val}, MACD {macd_val}, SMA downtrend confirmed."
        elif rsi_val != "N/A" and 45 <= rsi_val <= 55:
            verdict_status = "Neutral"
            verdict_msg = f"Final Verdict: Stock is {verdict_status}. Wait for Confirmation — RSI {rsi_val} indicates sideways momentum."
        else:
            verdict_status = "Mixed"
            verdict_msg = f"Final Verdict: