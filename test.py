"""
import finnhub
finnhub_client = finnhub.Client(api_key="cgg438hr01qgjoik89jgcgg438hr01qgjoik89k0")

print(finnhub_client.stock_candles('AAPL', 'D', 1679450400, 1679522400))
"""

import time
print(int(time.time()))

import datetime

def convert_day_to_unix(date):

    # Format input date to date format
    formated_date = datetime.datetime.strptime(date,"%Y-%m-%d")

    # Get unix timestamp for 11PM on that day
    unix_time = int(datetime.datetime.timestamp(formated_date) + 82800)

    # Return unix time stamp for the next working day (same day for Mo-Fr, next Monday for weekend)
    if datetime.datetime.weekday(formated_date) <= 4:
        return unix_time
    elif datetime.datetime.weekday(formated_date) == 5:
        return unix_time + 86400 * 2
    else:
        return unix_time + 86400

print(convert_day_to_unix("2023-04-01"))