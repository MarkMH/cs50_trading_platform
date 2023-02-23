import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd
from datetime import datetime

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


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
################################# Button that allows to add cash #################################

    # Initialize total_value
    total_value = 0

    # Get Portfolio (List of dictionaries) + Add to total_value
    portfolio = []
    for row in db.execute("SELECT * FROM portfolio WHERE user_id = ?", session["user_id"]):
        row['name'] = lookup(row['symbole'])['name']
        row['current_price'] = lookup(row['symbole'])['price']
        row['current_value'] = row['current_price'] * row['quantity']
        total_value += row['current_value']
        row['current_price'] = usd(row['current_price'])
        row['current_value'] = usd(row['current_value'])
        portfolio.append(row)

    # Get cash from users table
    cash = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])[0]['cash']

    # Calculate total value of portfolio
    total_value += cash
    return render_template("index.html", portfolio=portfolio, cash=usd(cash), total_value=usd(total_value))


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":

        # Validate Symbol
        if not request.form.get("symbol"):
            return apology("please provide a symbol")
        if lookup(request.form.get("symbol")) == None:
            return apology("this symbol does not exist")

        # Validate Quantity
        if not request.form.get("shares").isdigit():
            return apology("quantity must be an integer")

        if int(request.form.get("shares")) <= 0:
            return apology("only positive amounts can be bought")

        # Calculate purchase price
        name = lookup(request.form.get("symbol"))["name"]
        symbol = lookup(request.form.get("symbol"))["symbol"]
        price = lookup(request.form.get("symbol"))["price"]
        shares = int(request.form.get("shares"))
        order = shares * price

        # Validate if user has enough cash #current id = 2
        rows = db.execute("SELECT * FROM users WHERE id = ?", session["user_id"])

        if rows[0]["cash"] < order:
            return apology("not enough cash for this transaction")

        # Update Cash in SQL users Table
        else:
            db.execute("UPDATE users SET cash=? WHERE id=?", rows[0]["cash"] - order, session["user_id"])

        # Enter Transaction into histoy
        db.execute("INSERT INTO history (user_id, name, symbole, date, transaction_id, price, quantity) VALUES(?, ?, ?, ?, ?, ?, ?)",
                   session["user_id"], name, symbol, datetime.now(), "buy", price, shares)

        # Update Portfolio
        try:
            qty = db.execute("SELECT quantity FROM portfolio WHERE user_id = ? AND symbole = ?", session["user_id"], symbol)
            db.execute("UPDATE portfolio SET quantity=? WHERE user_id = ? AND symbole = ?",
                       qty[0]['quantity'] + shares, session["user_id"], symbol)
        except:
            db.execute("INSERT INTO portfolio (user_id, symbole, quantity) VALUES(?, ?, ?)",
                       session["user_id"], symbol, shares)

        return redirect("/")

    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    # History
    try:
        history = db.execute("SELECT * FROM history WHERE user_id = ?", session["user_id"])
        return render_template("history.html", history=history)
    except:
        return apology("No transacton made yet")


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

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

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":
        if lookup(request.form.get("symbol")) == None:
            return apology("this symbol does not exist")
        else:
            symbol = lookup(request.form.get("symbol"))
            symbol["price"] = usd(symbol["price"])
            return render_template("quoted.html", symbol=symbol)
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    # Forget any user_id
    session.clear()

    # Submission from register form
    if request.method == "POST":

        # Validate Input
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 400)

        # Ensure confirmation and password are identical
        elif request.form.get("password") != request.form.get("confirmation"):
            return apology("confirmation and password do not coincide", 400)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username does not exists
        if len(rows) >= 1:
            return apology("username has already been taken", 400)

        # Save new User
        db.execute("INSERT INTO users (username, hash) VALUES(?, ?)", request.form.get("username"),
                   generate_password_hash(request.form.get("password")))
        return redirect("/login")

    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
##################################### Not in History ##########################################

    symbols = db.execute("SELECT symbole FROM portfolio WHERE user_id = ?", session["user_id"])

    if request.method == "POST":
        # User needs to select a symbol
        if not request.form.get("symbol"):
            return apology("Please select a symbol")

        # User needs to select a symbol
        if not request.form.get("shares"):
            return apology("Please specify a quantity")

        # User needs to select a symbol
        if int(request.form.get("shares")) < 0:
            return apology("The quantity must be positive")

        # Check if user owns the symbol
        symbol = None
        for sym in symbols:
            if sym["symbole"] == request.form.get("symbol"):
                symbol = request.form.get("symbol")
        if not symbol:
            return apology("You do not own this stock")

        # Check if user has enough shares
        shares = db.execute("SELECT quantity FROM portfolio WHERE user_id = ? AND symbole = ?",
                            session["user_id"], symbol)[0]["quantity"]
        if shares < int(request.form.get("shares")):
            return apology("You do not own enough shares of this stock")

        # Enter Transaction into portfolio-table
            # Calculate new Quantity
        qty_new = shares - int(request.form.get("shares"))

        # Delete SQL entry in portfolio-table if new quantity 0
        if qty_new == 0:
            db.execute("DELETE FROM portfolio WHERE user_id = ? AND symbole = ?", session["user_id"], symbol)
        else:
            db.execute("UPDATE portfolio SET quantity=? WHERE user_id = ? AND symbole = ?", qty_new, session["user_id"], symbol)

        # Update cash balance in users-table according to current price
        price = lookup(symbol)["price"]
        order = int(request.form.get("shares")) * price
        cash = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])[0]['cash']
        db.execute("UPDATE users SET cash=? WHERE id=?", cash + order, session["user_id"])

        return redirect("/")
    else:
        return render_template("sell.html", symbols=symbols)


@app.route("/cash", methods=["GET", "POST"])
@login_required
def cash():
    """Add Cash to balance."""
    if request.method == "POST":

        # Ensure positive cash
        if int(request.form.get("cash")) < 0:
            return apology("cash must be positive", 400)

        # Update cash balance in users-table according to current price
        cash = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])[0]['cash']
        db.execute("UPDATE users SET cash=? WHERE id=?", cash + int(request.form.get("cash")), session["user_id"])
        return redirect("/")

    else:
        return render_template("cash.html")

# API key:  pk_e9a9f0a32f604ab8ab6c53a2d7b0eb7b

# 4. Index Page
# - Display:
#   - All stocks owned
#   - Number of shares for each stock
#   - Current Price of each stock
#   - Totoal Value of each holding
#   - Cuttent Cash balance
#   - Total Value

# 3. /buy
# - If GET: Display a form to buy the stock
#       - Symbol + Number of Shares
#       - Check for valid input (no negative number of shares - Symbol should be valid)
# - If POST: Purchase the stock
#       - Check if enough Cash for the purchase
#       - If not return apology
# - CREATE NEW TABLE: No table in the db that tracks what stocks user own
#       - Should represent users portfolio
# - Update Cash in existng TABLE

# 6. /history of all previous transactions:
# - One row for each burchase and sell
#   - Which Stock - How many units - When
# - Implementation depends on CREATE TABLE

# 2. "/quote" Look up a stock quote
# - If GET: Display a form to rquest a stock quote
# - If POST: Use lookup function for the requested stock quote
# - If lookup sucessfull: Returns a dictionary with name, price and symbol (probably use for loop for display)
# - If lookup not successfull: Returns NONE - create apology that informs user that this stock does not exist

# 1. Register (create new template similar to login.html),
# - Check for errors: If field is blank, passowrt not CONFIRMED, or username is already taken - return different apology
# - The entry extends the db: Use generate_password_hash and store that in db


# 5. Sell
# - If GET: Display Form that specifies symbole and quantity
# - If POST:
#   - Check for errors: No negative numbers - User actually has the number of stocks
#   - Sell Stocks
#   - Update cash balance accordingly

# 7. Personal Touch, i.e. new feature
# - For example:
#   - Change Passwort
#   - Add new Cash
#   - Short Selling?
#   - Clear all white space for log-in and registration