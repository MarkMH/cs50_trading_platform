import os
import io
from flask import Flask, flash, redirect, render_template, request, session
from matplotlib import pyplot as plt
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.security import check_password_hash, generate_password_hash
from db_connect import SQLiteConnector
import mplfinance as mpf
from datetime import date
import seaborn as sns
import pandas as pd
import base64
from django.conf import settings
from django.conf.urls.static import static


from helpers import (
    apology,
    login_required,
    usd,
    finnhub_quote,
    finnhub_candle,
    convert_day_to_unix,
    current_time_in_unix,
    get_price_one_year
)

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
# Make sure API key is set
# if not os.environ.get("API_KEY"):
#    raise RuntimeError("API_KEY not set")
# Configure CS50 Library to use SQLite database
db_connection = SQLiteConnector()

@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    # Get user id and portfolio from database
    user_id = session["user_id"]
    portfolio = db_connection.execute(
        "SELECT symbol, company_name, SUM(shares) AS shares FROM orders WHERE user_id=? GROUP BY symbol;",
        (user_id,),
    )

    # Get current stock prices and calculate value of portfolio (for each stock and total)
    total = 0
    for stock in portfolio:
        symbol = stock["symbol"].upper()
        stock["current_price"] = finnhub_quote(symbol)["price"]
        stock["total"] = float(stock["current_price"]) * stock["shares"]
        total = total + stock["total"]
        stock["total"] = usd(stock["total"])

    # Get current cash of user
    cash = db_connection.execute("SELECT cash FROM users WHERE id=?;", (user_id,))
    cash = float(cash[0]["cash"])

    # Calcuate total (portfolio and cash)
    total = usd(total + cash)

    """ Update open short orders (for all users) and close them if rebuy date is in past """
    open_short_orders = db_connection.execute("SElECT * FROM short WHERE rebuy_price IS NULL;")
    # get current time in unix
    for short in open_short_orders:
        # Convert rebuy_date to unix time stamp of the current day / next trading day at 11pm
        rebuy_date = convert_day_to_unix(short["rebuy_date"])

        # Get current time as unix time stamp
        current_time = current_time_in_unix()

        # Close order if rebuy date is in the past
        if rebuy_date <= current_time:
            short_id = int(short["short_id"])
            shares = int(short["shares"])
            symbol = short["symbol"].upper()
            sell_price = float(short["sell_price"])

            # Get price from Finnhub and calculate profit
            rebuy_price = float(finnhub_candle(symbol, rebuy_date)["price"])
            profit = round(shares * (sell_price - rebuy_price), 2)

            # Update data base
            db_connection.execute(
                "UPDATE short SET rebuy_price = ?, profit = ? WHERE short_id = ?;",
                (rebuy_price,
                profit,
                short_id,)
            )

    """ List remaining open short orders (only for logged in user) """
    open_short_orders = db_connection.execute(
        "SELECT * FROM short WHERE rebuy_price IS NULL AND user_id = ?;", (user_id,)
    )
    for short in open_short_orders:
        symbol = short["symbol"].upper()
        current_price = float(finnhub_quote(symbol)["price"])
        short["current_profit"] = usd(
            int(short["shares"]) * (float(short["sell_price"]) - current_price)
        )
        short["current_price"] = usd(current_price)

    return render_template(
        "index.html",
        portfolio=portfolio,
        cash=usd(cash),
        total=total,
        shorts=open_short_orders,
    )


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    if request.method == "POST":
        # Ensure that symbol was submitted
        if not request.form.get("symbol"):
            return apology("must provide a symbol")

        # Ensure that symbol exists
        elif not finnhub_quote(request.form.get("symbol")):
            return apology("this symbol does not exist")

        # Ensure that number of shares was submitted
        elif not request.form.get("shares"):
            return apology("must provide number of shares")

        # Buy stock for user
        else:
            # Ensure that number of shares is an integer
            try:
                shares = int(request.form.get("shares"))
            except:
                return apology("number of shares must be positive integer")

            # Ensure that number of shares is positive
            if shares < 1:
                return apology("number of shares must be positive")

            # Get stock data
            symbol = request.form.get("symbol").upper()
            price = finnhub_quote(symbol)["price"]

            # Check whether symbol exists on API
            if int(price) == 0:
                return apology("This symbol does not exist")

            # Get number of shares
            shares = request.form.get("shares")

            # Get data on user and calculate cost of order
            cost = int(shares) * float(price)

            # Verify whether user has enough cash for buy order
            user_id = session["user_id"]
            cash = db_connection.execute("SELECT cash FROM users WHERE id = ?;", (user_id, ))[0][
                "cash"
            ]
            if cash < cost:
                return apology("you cannot afford this order")

            # Update order table and user's cash
            else:
                db_connection.execute(
                    "INSERT INTO orders (symbol, price, shares, user_id, date) VALUES (?, ?, ?, ?, datetime());",
                    (symbol,
                    price,
                    shares,
                    user_id,)
                )
                db_connection.execute(
                    "UPDATE users SET cash = ? WHERE id = ?;", (cash - cost, user_id,)
                )

            # After successful buy, redirect to index page
            return redirect("/")

    # User reached route via GET
    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    orders = db_connection.execute("SELECT * FROM orders WHERE user_id = ?;", (session["user_id"],))
    closed_short_orders = db_connection.execute(
        "SELECT * FROM short WHERE (rebuy_price IS NOT NULL) AND user_id = ?;",
        (session["user_id"],)
    )
    return render_template(
        "history.html", orders=orders, closed_short_orders=closed_short_orders
    )


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username")

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password")

        # Query database for username
        rows = db_connection.execute(
            "SELECT * FROM users WHERE username = ?", (request.form.get("username"),)
        )

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(
            rows[0]["hash"], request.form.get("password")
        ):
            return apology("invalid username and/or password")

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login formquoteloo
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":
        # Ensure that symbol was submitted
        if not request.form.get("symbol"):
            return apology("must provide a symbol")

        # Ensure that symbol exists
        elif int(finnhub_quote(request.form.get("symbol"))["price"]) == 0:
            return apology("this symbol does not exist")

        # Show quote to user
        else:     
            symbol = request.form.get("symbol").upper()
            price = finnhub_quote(symbol)["price"]      
            
            df = pd.DataFrame(get_price_one_year(symbol, date.today()))
            df['t'] = pd.to_datetime(df['t'], unit='s')
            #df['t'] = df['t'].dt.strftime('%Y-%m-%d')

            df.rename(columns = {
                'o': 'Open',
                'h': 'High',
                'l': 'Low',
                'c': 'Close',
                'v': 'Volume'
            }, inplace=True
            )

            print(df.head())

            # Set the DataFrame index to the datetime column
            df.set_index('t', inplace=True)

            # Create the candlestick plot
            mpf.plot(df, type='candle', style='charles', ylabel='Price')

            # Create the candlestick plot with modified parameters
            fig, ax = mpf.plot(df, type='candle', style='charles', ylabel='Price', returnfig=True,
                   figratio=(25, 14), scale_width_adjustment=dict(candle=0.8, candle_linewidth=0.8),
                   title=f"{symbol} Stock Price for Last Year")

            # Save the plot as an image
            img = io.BytesIO()
            fig.savefig(img, format="png")
            img.seek(0)

            # Encode the image in base64 and convert it to a data URI
            encoded = base64.b64encode(img.getvalue()).decode("utf-8")
            data_uri = "data:image/png;base64,{}".format(encoded)

            return render_template(
                "quoted.html", symbol=symbol, price=usd(float(price)), plot=data_uri
            )
        
            

    # User reached route via GET
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":
        # Get username from the form
        username = request.form.get("username")
        registered_users = db_connection.execute("SELECT username FROM users;")
        registered_usernames = [
            registered_users[i]["username"] for i in range(len(registered_users))
        ]

        # Ensure username was submitted
        if not username:
            return apology("must provide username")

        # Ensure username is not already used
        elif username in registered_usernames:
            return apology("username already used")

        # Get password from user
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")

        # Ensure password was submitted
        if not password:
            return apology("must provide password")

        # Ensure password an confirmation match
        elif password != confirmation:
            return apology("password and confirmation do not match")

        # Insert user and password into database
        else:
            db_connection.execute(
                "INSERT INTO users (username, hash) VALUES (?, ?);",
                (username,
                generate_password_hash(password),)
            )

        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    # Check which stocks the user should be able to select to sell (those that are in the portfolio)
    user_id = session["user_id"]
    portfolio = db_connection.execute(
        "SELECT symbol, SUM(shares) AS shares FROM orders WHERE user_id=? GROUP BY symbol;",
        (user_id,)
    )
    stocks_to_sell = [stock["symbol"] for stock in portfolio]
    print(stocks_to_sell)

    # User sumbitted a form
    if request.method == "POST":
        symbol = request.form.get("symbol")

        # Check wether shares input is a number
        try:
            shares_to_sell = int(request.form.get("shares"))
        except:
            return apology("submit a positive integer")

        # Check whether number to sell is positive integer
        if shares_to_sell < 1:
            return apology("submit positive number")

        # Go through all stocks in portfolio to check whether the stock to sell is in the current portfolio
        for stock in portfolio:
            if stock["symbol"].upper() == symbol.upper():
                # Check whether there are enough shares in the portfolio
                if int(stock["shares"]) < shares_to_sell:
                    return apology("you do not have enough of these shares to sell")

                # Execute order and put sell in orders table (as negative number of shares to sell!) and update cash in users table
                else:
                    # Get stock data from API
                    symbol = symbol.upper()
                    price = finnhub_quote(symbol)["price"]

                    # Put order in oders table
                    db_connection.execute(
                        "INSERT INTO orders (symbol, price, shares, user_id, date) VALUES (?, ?, ?, ?, datetime());",
                        (symbol,
                        price,
                        -shares_to_sell,
                        user_id,)
                    )

                    # Update cash in users table
                    cash = db_connection.execute("SELECT cash FROM users WHERE id = ?;", (user_id,))[
                        0
                    ]["cash"]
                    new_cash = float(cash) + shares_to_sell * float(price)
                    db_connection.execute(
                        "UPDATE users SET cash = ? WHERE id = ?;", (new_cash, user_id,)
                    )

                    # Redirect to index
                    return redirect("/")
            else:
                continue

        # If the user does not have the stock to sell in the portfolio at all
        return apology("you do not have this stock in portfolio")

    # User reached route via GET
    else:
        return render_template("sell.html", stocks_to_sell=stocks_to_sell)


@app.route("/cash", methods=["GET", "POST"])
@login_required
def cash():
    """Let user add cash to account"""

    # User reached route via POST (submitting a form)
    if request.method == "POST":
        if not request.form.get("cash"):
            return apology("submit a number..")
        else:
            add_cash = int(request.form.get("cash"))
            user_id = session["user_id"]
            cash = db_connection.execute("SELECT cash FROM users WHERE id = ?;", (user_id,))[0][
                "cash"
            ]
            new_cash = cash + add_cash
            db_connection.execute("UPDATE users SET cash = ? WHERE id = ?;", (new_cash, user_id,))
            return redirect("/")

    # User reached route via GET
    else:
        return render_template("cash.html")


@app.route("/leaderboard", methods=["GET"])
@login_required
def leaderboard():
    """Let users compare their own performance to other users"""
    # Initialize list of performances (one entry for each user)
    performance_list = []

    # Get all users and their cash by id
    users = db_connection.execute("SELECT id, username, cash FROM users;")

    # Get all stock orders (aggregated by symbol) for all users
    stock_orders = db_connection.execute(
        "SELECT user_id, symbol, SUM(shares) AS shares FROM orders GROUP BY symbol, user_id;"
    )

    # Get all (finished) short orders
    short_orders = db_connection.execute(
        "SELECT user_id, SUM(profit) AS profit FROM short WHERE rebuy_price IS NOT NULL GROUP BY user_id;"
    )

    # For each user calculate value of portfolio
    for user in users:
        performance = dict()
        user_id = user["id"]
        performance["username"] = user["username"]

        # Calcuate total value of stock portfolio
        performance["stocks"] = 0
        for stock_order in stock_orders:
            if stock_order["user_id"] == user_id:
                symbol = stock_order["symbol"].upper()
                price = float(finnhub_quote(symbol)["price"])
                performance["stocks"] += int(stock_order["shares"]) * price

        # Calculate total profit from short orders
        performance["short"] = 0
        for short_order in short_orders:
            if short_order["user_id"] == user_id:
                performance["short"] = float(short_order["profit"])

        # Get current cash
        performance["cash"] = user["cash"]

        # Compute total performance
        performance["total"] = (
            performance["stocks"] + performance["cash"] + performance["short"]
        )

        # Format nicely
        performance["stocks"] = usd(performance["stocks"])
        performance["short"] = usd(performance["short"])
        performance["cash"] = usd(performance["cash"])
        performance["total"] = usd(performance["total"])

        # Append individual performance to overall lust
        performance_list = performance_list + [performance]

    # Sort the full list of performances
    performance_list_sorted = sorted(
        performance_list, key=lambda d: d["total"], reverse=True
    )

    # Assign rank variable
    rank = 1
    for performance in performance_list_sorted:
        performance["rank"] = rank
        rank += 1

    # Render template and leaderboard
    return render_template("leaderboard.html", performance=performance_list_sorted)


@app.route("/short", methods=["POST", "GET"])
@login_required
def short():
    """Let user go short on a stock"""

    # User submits a form
    if request.method == "POST":
        user_id = session["user_id"]

        # Get user input
        symbol = request.form.get("symbol").upper()
        shares = request.form.get("shares")
        rebuy_date = request.form.get("rebuy_date")

        # Check whether user input is valid
        # Check if symbol provided
        if not symbol:
            return apology("submit a symbol")

        # Check if shares provided
        elif not shares:
            return apology("submit number of shares")

        # Check if date provided
        elif not rebuy_date:
            return apology("submit a rebuy date")

        else:
            try:
                shares = int(request.form.get("shares"))
            except:
                return apology("submit a positive integer")

            # Check whether number to sell is positive integer
            if shares < 1:
                return apology("submit positive number")

            # Get price
            price = finnhub_quote(request.form.get("symbol"))["price"]

            # Check whether symbol exists
            if int(price) == 0:
                return apology("This symbol does not exist")

            # Execute order
            else:
                db_connection.execute(
                    "INSERT INTO short (user_id, symbol, sell_price, shares, date, rebuy_date) VALUES (?, ?, ?, ?, datetime(), ?);",
                    (user_id,
                    symbol,
                    price,
                    shares,
                    rebuy_date,)
                )

        return redirect("/")

    # User reached route via GET
    else:
        return render_template("short.html")
    