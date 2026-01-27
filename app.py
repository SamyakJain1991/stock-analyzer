from flask import Flask, render_template, request
import yfinance as yf
import numpy as np
from finta import TA
import os

app = Flask(__name__)

@app.route('/', methods=['GET', 'POST'])
def index():
    error = None
    data = None
    ticker = ""

    if request.method == 'POST':
        ticker = request.form.get('ticker', '').strip().upper()

        # Auto-append .NS if missing
        if not ticker.endswith('.NS') and not ticker.endswith('.BO'):
            ticker += '.NS'

        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="6mo")

            if hist.empty:
                error = f"No data found for {ticker}"
            else:
                hist = hist.dropna()
                hist['SMA_20'] = TA.SMA(hist, 20)
                hist['SMA_50'] = TA.SMA(hist, 50)
                hist['RSI'] = TA.RSI(hist)

                latest = hist.iloc[-1]
                data = {
                    'ticker': ticker,
                    'close': round(latest['Close'], 2),
                    'sma_20': round(latest['SMA_20'], 2),
                    'sma_50': round(latest['SMA_50'], 2),
                    'rsi': round(latest['RSI'], 2)
                }

        except Exception as e:
            if "Rate limited" in str(e):
                error = "Yahoo Finance rate limit reached. Please try again after a few minutes."
            else:
                error = f"Error: {str(e)}"

    return render_template('index.html', error=error, data=data)

if __name__ == '__main__':
    # Render requires binding to 0.0.0.0 and PORT env variable
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)