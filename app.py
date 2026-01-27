from flask import Flask, request, jsonify, render_template
import yfinance as yf
import numpy as np
from finta import TA
import os

app = Flask(__name__)

@app.route('/')
def home():
    # Initial page load without analysis
    return render_template('index.html', analysis=None)

@app.route('/analyze')
def analyze():
    raw_input = request.args.get('ticker', default='RELIANCE', type=str)
    ticker = raw_input.strip().upper().replace(" ", "").replace(",", "")

    if not ticker.endswith(".NS") and not ticker.endswith(".BO"):
        ticker += ".NS"

    data = yf.download(ticker, period='6mo', interval='1d')
    if data.empty:
        return render_template('index.html', analysis={'error': f'No data found for {ticker}'})

    data = data.dropna()

    # --- Trend Analysis ---
    data['SMA_10'] = TA.SMA(data, 10)
    data['SMA_30'] = TA.SMA(data, 30)
    trend = "UP" if data['SMA_10'].iloc[-1] > data['SMA_30'].iloc[-1] else "DOWN"
    trend_msg = (
        "Stock abhi uptrend me hai (short-term average upar hai)."
        if trend == "UP"
        else "Stock abhi downtrend me hai (short-term average neeche hai)."
    )

    # --- Entry Strategy ---
    data['RSI'] = TA.RSI(data)
    data['MACD'] = TA.MACD(data)['MACD']
    entry_price = round(data['Close'].iloc[-1], 2)
    entry_range = f"{entry_price - 20:.2f} – {entry_price:.2f}"
    invalidation = f"{entry_price - 30:.2f}"
    entry_msg = (
        f"RSI {data['RSI'].iloc[-1]:.2f} (30 se neeche matlab oversold), "
        f"MACD {data['MACD'].iloc[-1]:.2f}. "
        f"Kharidne ka zone {entry_range}. Agar {invalidation} se neeche gaya to trade avoid karo."
    )

    # --- Exit Strategy ---
    exit_msg = (
        f"Profit jaldi lena ho to {entry_price + 50:.2f} ke aas-paas exit karo. "
        f"Safe exit {entry_price + 25:.2f} ke aas-paas hai."
    )

    # --- Stop-loss Strategy ---
    stop_loss = f"{entry_price - 25:.2f}"
    stoploss_msg = (
        f"Stop-loss {stop_loss} rakho. Agar stock us level se neeche gaya to turant exit karo. "
        "Ek trade me apne capital ka sirf 1–2% risk lo."
    )

    # --- Final Verdict ---
    verdict = "Trade confidently" if trend == "UP" and data['Volume'].iloc[-1] > data['Volume'].tail(10).mean() else "Trade cautiously"
    verdict_msg = (
        f"{verdict} — "
        + (
            "trend strong hai aur liquidity healthy hai."
            if verdict == "Trade confidently"
            else "stock weak hai, isliye carefully trade karo. Volume theek hai."
        )
    )

    # --- Company Info ---
    info = yf.Ticker(ticker).info
    company_name = info.get("longName", "N/A")
    sector = info.get("sector", "N/A")
    description = info.get("longBusinessSummary", "N/A")

    # Analysis dict for template
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

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)