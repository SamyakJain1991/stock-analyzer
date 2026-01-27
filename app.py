from flask import Flask, request, jsonify, send_from_directory
import yfinance as yf
import numpy as np
import talib

app = Flask(__name__)

# Serve frontend file directly from Flask
@app.route('/')
def home():
    return send_from_directory('.', 'index.html')

@app.route('/analyze')
def analyze():
    # Get ticker from user
    ticker = request.args.get('ticker', default='RELIANCE', type=str).upper()

    # Always append .NS for Indian NSE stocks
    if not ticker.endswith(".NS"):
        ticker = ticker + ".NS"

    # Fetch last 6 months daily data
    data = yf.download(ticker, period='6mo', interval='1d')

    if data.empty:
        return jsonify({'error': f'No data found for {ticker}'}), 404

    # Convert to 1D numpy arrays
    close = data['Close'].to_numpy().astype(float).flatten()
    high = data['High'].to_numpy().astype(float).flatten()
    low = data['Low'].to_numpy().astype(float).flatten()
    volume = data['Volume'].to_numpy().astype(float).flatten()

    # --- Trend Analysis ---
    sma_short = talib.SMA(close, timeperiod=10)
    sma_long = talib.SMA(close, timeperiod=30)
    trend = "UP" if sma_short[-1] > sma_long[-1] else "DOWN"
    trend_msg = (
        "Stock abhi uptrend me hai (short-term average upar hai)."
        if trend == "UP"
        else "Stock abhi downtrend me hai (short-term average neeche hai)."
    )

    # --- Entry Strategy ---
    rsi = talib.RSI(close, timeperiod=14)
    macd, macdsignal, macdhist = talib.MACD(close, fastperiod=12, slowperiod=26, signalperiod=9)
    entry_price = round(close[-1], 2)
    entry_range = f"{entry_price - 20:.2f} – {entry_price:.2f}"
    invalidation = f"{entry_price - 30:.2f}"
    entry_msg = (
        f"RSI {rsi[-1]:.2f} (30 se neeche matlab oversold), MACD {macd[-1]:.2f}. "
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
    verdict = "Trade confidently" if trend == "UP" and volume[-1] > np.mean(volume[-10:]) else "Trade cautiously"
    verdict_msg = (
        f"{verdict} — "
        + (
            "trend strong hai aur liquidity healthy hai."
            if verdict == "Trade confidently"
            else "stock weak hai, isliye carefully trade karo. Volume theek hai."
        )
    )

    return jsonify({
        "Trend": trend_msg,
        "Entry": entry_msg,
        "Exit": exit_msg,
        "StopLoss": stoploss_msg,
        "Verdict": verdict_msg
    })

if __name__ == '__main__':
    app.run(debug=True)