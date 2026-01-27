from flask import Flask, render_template, request
import yfinance as yf
import pandas as pd
from finta import TA
import os

# Tell Flask to look for templates in current folder
app = Flask(__name__, template_folder=os.path.dirname(os.path.abspath(__file__)))

@app.route("/", methods=["GET", "POST"])
def index():
    analysis = None
    if request.method == "POST":
        ticker = request.form["ticker"].upper()
        try:
            # Stock data download
            df = yf.download(ticker, period="6mo", interval="1d")

            if df.empty:
                analysis = {"error": f"No data found for {ticker}"}
            else:
                # Technical indicators using finta
                df["RSI"] = TA.RSI(df)
                macd = TA.MACD(df)
                df["MACD"] = macd["MACD"]
                df["Signal"] = macd["SIGNAL"]
                df["EMA"] = TA.EMA(df)

                # Latest values
                latest = df.iloc[-1]
                analysis = {
                    "ticker": ticker,
                    "close": round(latest["Close"], 2),
                    "rsi": round(latest["RSI"], 2),
                    "macd": round(latest["MACD"], 2),
                    "signal": round(latest["Signal"], 2),
                    "ema": round(latest["EMA"], 2),
                }
        except Exception as e:
            analysis = {"error": str(e)}

    return render_template("index.html", analysis=analysis)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)