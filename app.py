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
            last_price = nse_data.get("priceInfo", {}).get("lastPrice", "N/A")

            analysis = {
                "ticker": raw_input,
                "Company": company_name,
                "Sector": sector,
                "Description": "NSE data available",
                "Trend": "Trend Analysis: NSE data fetched successfully.",
                "Entry": f"Entry Strategy: Current price {last_price}. Use NSE chart for RSI/MACD.",
                "Exit": "Exit Strategy: Use NSE chart for exit strategy.",
                "StopLoss": "Stop-Loss Strategy: Use NSE chart for stop-loss.",
                "Verdict": "Final Verdict: Data from NSE India API."
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
        entry_range = f"{entry_price - 20} – {entry_price}" if entry_price != "N/A" else "N/A"
        invalidation = f"{entry_price - 30}" if entry_price != "N/A" else "N/A"
        entry_msg = f"Entry Strategy: RSI {safe_val(data['RSI'])}, MACD {safe_val(data['MACD'])}. Zone {entry_range}. Invalidation {invalidation}."

        # Exit Strategy
        exit_msg = f"Exit Strategy: Exit around {entry_price + 50}" if entry_price != "N/A" else "Exit Strategy: N/A"

        # Stop-loss Strategy
        stop_loss = f"{entry_price - 25}" if entry_price != "N/A" else "N/A"
        stoploss_msg = f"Stop-Loss Strategy: Stop-loss {stop_loss} rakho."

        # Final Verdict
        verdict = "Trade confidently" if trend == "UP" and entry_price != "N/A" and data['Volume'].iloc[-1] > data['Volume'].tail(10).mean() else "Trade cautiously"
        verdict_msg = f"Final Verdict: {verdict} — liquidity check done."

        try:
            info = yf.Ticker(str(ticker)).info or {}
        except Exception:
            info = {}
        company_name = info.get("longName", ticker)
        sector = info.get("sector", "N/A")
        description = info.get("longBusinessSummary", "N/A")

        analysis = {
            "ticker": ticker,
            "Company": company_name,
            "Sector": sector,
            "Description": description,
            "Trend": trend_msg,
            "Entry": entry_msg,
            "Exit": exit_msg,
            "StopLoss": stoploss_msg,
            "Verdict": verdict_msg
        }

        return render_template('index.html', analysis=analysis)

    except Exception as e:
        return render_template('index.html', analysis={'error': f'Unexpected error: {str(e)}'})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)