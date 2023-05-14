import os
import requests
import urllib.parse
import finnhub
import time
import datetime
import time


from flask import redirect, render_template, request, session
from functools import wraps


finnhub_client = finnhub.Client(api_key="cgg438hr01qgjoik89jgcgg438hr01qgjoik89k0")


def apology(message, code=400):
    """Render message as an apology to user."""

    def escape(s):
        """
        Escape special characters.

        https://github.com/jacebrowning/memegen#special-characters
        """
        for old, new in [
            ("-", "--"),
            (" ", "-"),
            ("_", "__"),
            ("?", "~q"),
            ("%", "~p"),
            ("#", "~h"),
            ("/", "~s"),
            ('"', "''"),
        ]:
            s = s.replace(old, new)
        return s

    return render_template("apology.html", top=code, bottom=escape(message)), code


def login_required(f):
    """
    Decorate routes to require login.

    https://flask.palletsprojects.com/en/1.1.x/patterns/viewdecorators/
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("user_id") is None:
            return redirect("/login")
        return f(*args, **kwargs)

    return decorated_function

def usd(value):
    """Format value as USD."""
    return f"${value:,.2f}"


def finnhub_quote(symbol):
    return {"price": float(finnhub_client.quote(symbol)["c"]), "symbol": symbol.upper()}


def get_price_one_year(symbol, date):
    end_day = int(date.strftime("%s"))
    start_day = int((date - datetime.timedelta(days=365)).strftime("%s"))
    
    return finnhub_client.stock_candles(symbol, 'D', start_day, end_day)
    
    


def finnhub_candle(symbol, date):
    end_unix = date
    start_unix = end_unix - 72000
    candle = finnhub_client.stock_candles(symbol, "D", start_unix, end_unix)
    try:
        return {"price": float(candle["c"][0]), "symbol": symbol.upper()}
    except:
        return {"price": float(candle["o"][0]), "symbol": symbol.upper()}


# Convert a datetime to the unix time of that day (or the next weekday) on 11:00 PM
def convert_day_to_unix(date):
    # Format input date to date format
    formated_date = datetime.datetime.strptime(date, "%Y-%m-%d")

    # Get unix timestamp for 11PM on that day
    unix_time = int(datetime.datetime.timestamp(formated_date) + 82800)

    # Return unix time stamp for the next working day (same day for Mo-Fr, next Monday for weekend)
    if datetime.datetime.weekday(formated_date) <= 4:
        return unix_time
    elif datetime.datetime.weekday(formated_date) == 5:
        return unix_time + 86400 * 2
    else:
        return unix_time + 86400
    


# Return the current local time in unix
def current_time_in_unix():
    return int(time.time())
