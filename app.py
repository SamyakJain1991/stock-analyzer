from flask import Flask, request, render_template
import yfinance as yf
import numpy as np
from finta import TA
import os

app = Flask(__name__)

# --- Alias mapping for common tickers (NSE format) ---
ALIASES = {
    "INFOSYS": "INFY.NSE",
    "TCS": "TCS.NSE",
    "RELIANCE": "RELIANCE.NSE",
    "HDFC": "HDFCBANK.NSE",
    "SBIN": "SBIN.NSE",
    "ICICI": "ICICIBANK.NSE"
}

# --- Universal sanitizer for ticker input ---
def sanitize_ticker(raw_input):
    if raw_input is None:
        return "RELIANCE"
    # Handle nested tuple/list until string
    while isinstance(raw_input, (list, tuple)):
        if len(raw_input) == 0:
            return "RELIANCE"
        raw_input = raw_input[0]
    # Force string
    return str(raw_input).strip().upper().replace(" ", "").replace(",", "")

@app.route('/')
def home():
    return render_template('index.html', analysis=None)

@app.route('/analyze')
def analyze():
    try:
        # --- Get ticker safely ---
        raw_input = request.args.get('ticker', default='RELIANCE')
        raw_input = sanitize_ticker(raw_input)

        # Apply alias mapping
        ticker = str(ALIASES.get(raw_input, raw_input))

        # Append NSE suffix if missing
        if not ticker.endswith(".NSE") and not ticker.endswith(".BO"):
            ticker = ticker + ".NSE"

        # Final force cast
        ticker = str(ticker)

        # --- Download data ---
        data = yf.download(ticker, period='6mo', interval='1d')
        if data.empty:
            return render_template('index.html', analysis={'error': f'No data found for {ticker}'})

        data = data.dropna()

        # --- Safe helper for indicators ---
        def safe_val(series, default="N/A"):
            try:
                val = series.iloc[-1]
                if np.isnan(val):
                    return default
                return round(val, 2)
            except Exception:
                return default

        # --- Trend Analysis ---
        data['SMA_10'] = TA.SMA(data, 10)
        data['SMA_30'] = TA.SMA(data, 30)
        sma10 = safe_val(data['SMA_10'])
        sma30 = safe_val(data['SMA_30'])
        trend = "UP" if sma10 != "N/A" and sma30 != "N/A" and sma10 > sma30 else "DOWN"
        trend_msg = "Stock abhi uptrend me hai." if trend == "UP" else "Stock abhi downtrend me hai."

        # --- Entry Strategy ---
        data['RSI'] = TA.RSI(data)
        data['MACD'] = TA.MACD(data)['MACD']
        entry_price = safe_val(data['Close'])
        entry_range = f"{entry_price - 20} – {entry_price}" if entry_price != "N/A" else "N/A"
        invalidation = f"{entry_price - 30}" if entry_price != "N/A" else "N/A"
        entry_msg = f"RSI {safe_val(data['RSI'])}, MACD {safe_val(data['MACD'])}. Zone {entry_range}. Invalidation {invalidation}."

        # --- Exit Strategy ---
        exit_msg = f"Exit around {entry_price + 50}" if entry_price != "N/A" else "N/A"

        # --- Stop-loss Strategy ---
        stop_loss = f"{entry_price - 25}" if entry_price != "N/A" else "N/A"
        stoploss_msg = f"Stop-loss {stop_loss} rakho."

        # --- Final Verdict ---
        verdict = "Trade confidently" if trend == "UP" and entry_price != "N/A" and data['Volume'].iloc[-1] > data['Volume'].tail(10).mean() else "Trade cautiously"
        verdict_msg = f"{verdict} — liquidity check done."

        # --- Company Info ---
        try:
            info = yf.Ticker(ticker).info or {}
        except Exception:
            info = {}
        company_name = info.get("longName", ticker)
        sector = info.get("sector", "N/A")
        description = info.get("longBusinessSummary", "N/A")

        # --- Analysis dict for template ---
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