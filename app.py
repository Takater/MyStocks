import os

from cs50 import SQL
from flask import Flask, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash
from dotenv import load_dotenv

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Load .env
load_dotenv()

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.getenv("API_KEY"):
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
    # Owned stocks
    stocks = db.execute("SELECT * FROM purchases WHERE buyer_id = ?", session["user_id"])

    # Current cash
    curr_cash = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])[0]["cash"]

    # Current total balance and owned stock prices
    balance = curr_cash
    for stock in stocks:
        stock_curr = lookup(stock['stock'])
        stock['price'] = stock_curr['price']
        stock['total'] = stock['price'] * stock['shares']
        balance += stock['total']

    # Open homepage
    return render_template("index.html", stocks=stocks, curr_cash=curr_cash, balance=balance)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    # POST method
    if request.method == "POST":

        # Get user id
        user_id = session["user_id"]

        # Get chosen symbol and check if it exists
        symbol = request.form.get("symbol")
        stock = lookup(symbol)
        if stock == None:
            return apology("Stock doesn't exist")

        # Get chosen number of shares and check if it's valid
        shares = request.form.get("shares")
        if not shares or (shares.isdigit() == False) or int(shares) < 1:
            return apology("Invalid number of shares")

        # Validated form

        # Get chosen stock's price and total (price * shares)
        price = stock['price']
        total = price * int(shares)

        # Check if user has enough cash for the purchase
        current_cash = db.execute("SELECT * FROM users WHERE id = ?", user_id)[0]["cash"]
        if current_cash < total:
            return apology("You don't have enough cash for this purchase")

        # Update databases
        else:
            
            # Check if user already owns any shares of stock
            owned_stocks = db.execute("SELECT stock FROM purchases WHERE buyer_id = ?", user_id)
            curr_stocks = []
            for row in owned_stocks:
                curr_stocks.append(row['stock'])
                
            # If user already owns stock, updates user shares
            if symbol in curr_stocks:
                curr_shares = int(db.execute("SELECT shares FROM purchases WHERE buyer_id = ? AND stock = ?", user_id, symbol)[0]["shares"])
                db.execute("UPDATE purchases SET shares = ? WHERE buyer_id = ? AND stock = ?", curr_shares + int(shares), user_id, symbol)
            else:
                
                # If user doesn't own stock, insert stock into user's purchases
                db.execute("INSERT INTO purchases(buyer_id, stock, price, shares) VALUES(?, ?, ?, ?)", user_id, symbol, price, shares)

            # Insert purchase into user's history
            db.execute("INSERT INTO history(buyer_id, type, stock, price, shares, time) VALUES(?, ?, ?, ?, ?, strftime('%d/%m/%Y | %H:%M', datetime()))",
                       user_id, "BUY", symbol, price, shares)

            # Update user's cash
            db.execute("UPDATE users SET cash = ? WHERE id = ?", (current_cash - total), user_id)

            # Return to homepage
            return redirect('/')

    # GET method
    else:
        # Check if user comes from home page button
        if not request.args.get('symbol'):

            # No chosen symbol yet
            return render_template("buy.html")
        else:

            # Chosen symbol from homepage
            return render_template("buy.html", symbol=request.args.get('symbol'))

# Route to check symbol price or user info


@app.route("/search")
@login_required
def search():

    # Get symbol and user id
    symbol = request.args.get('symbol')
    user = session["user_id"]

    if not symbol:

        # No symbol, return user info
        user_c = db.execute("SELECT * FROM users WHERE id = ?", user)
        return user_c[0]

    else:
        # Check if symbol exists and return info
        stocks = lookup(symbol)
        if stocks != None:
            return stocks
        else:
            return apology("Stock doesn't exist")


@app.route("/history")
@login_required
def history():

    # Open template with user's transaction history
    history = db.execute("SELECT * FROM history WHERE buyer_id = ?", session["user_id"])
    return render_template("history.html", history=history)


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
        
        # If it's test credentials, restart purchases
        if db.execute("SELECT username FROM users WHERE id = ?", session["user_id"])[0]["username"] == "testuser":
            db.execute("UPDATE users SET cash=10000 WHERE id = ?", session["user_id"])
            db.execute("DELETE FROM purchases WHERE buyer_id = ?", session["user_id"])
            db.execute("DELETE FROM history WHERE buyer_id = ?", session["user_id"])

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""
    if db.execute("SELECT username FROM users WHERE id = ?", session["user_id"])[0]["username"] == "testuser":
        db.execute("UPDATE users SET cash=10000 WHERE id = ?", session["user_id"])
        db.execute("DELETE FROM purchases WHERE buyer_id = ?", session["user_id"])
        db.execute("DELETE FROM history WHERE buyer_id = ?", session["user_id"])

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():

    # POST method
    if request.method == "POST":

        # Get symbol from form and ensure it's valid
        stocks = lookup(request.form.get("symbol"))
        if stocks == None:
            return apology("Stock doesn't exist")
        else:

            # Return template with stock info
            return render_template("quoted.html", stocks=stocks)

    # GET method, open template with form
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    # POST method (registration form answered)
    if request.method == "POST":

        # Check for username and ensure it's not already in use
        username = request.form.get("username")
        if not username:
            return apology("Missing username")
        checkuser = db.execute("SELECT * FROM users WHERE username = ?", username)
        if len(checkuser) != 0:
            return apology("Username already in use")

        # Get chosen password and confirmation and ensure they're valid and the same
        password = request.form.get("password")
        confirm = request.form.get("confirmation")
        if not password or not confirm:
            return apology("Missing password")
        if password != confirm:
            return apology("Password and confirmation don't match")

        # Validated form

        # Insert user in database
        db.execute("INSERT INTO users(username, hash) VALUES(?, ?)", username, generate_password_hash(password))

        # Return to home page
        return redirect("/")

    # GET method (open registration form)
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    # POST method
    if request.method == "POST":

        # User id
        user_id = session["user_id"]

        # Chosen stock
        symbol = request.form.get("symbol")

        # Ensure user owns chosen stock
        owned_stocks = db.execute("SELECT stock FROM purchases WHERE buyer_id = ?", user_id)
        curr_stocks = []
        for row in owned_stocks:
            curr_stocks.append(row['stock'])
        if symbol not in curr_stocks:
            return apology("You don't own this stock")

        # Ensure user provided a valid number of shares for chosen stock
        shares = int(request.form.get("shares"))
        curr_shares = db.execute("SELECT shares FROM purchases WHERE stock = ? AND buyer_id = ?", symbol, user_id)[0]["shares"]
        if shares < 1 or shares > curr_shares:
            return apology("You don't own these many shares for this stock")

        # Validated form

        # Current cash, price and total for chosen stock
        stock = lookup(symbol)
        price = float(stock['price'])
        current_cash = float(db.execute("SELECT * FROM users WHERE id = ?", user_id)[0]["cash"])
        total = float(price * shares)

        # Update number of shares or delete stock
        if (curr_shares - shares) == 0:
            db.execute("DELETE FROM purchases WHERE stock = ?", symbol)
        else:
            db.execute("UPDATE purchases SET shares = ? WHERE stock = ?", (curr_shares - shares), symbol)

        # Update user's current cash
        db.execute("UPDATE users SET cash = ? WHERE id = ?", (current_cash + total), user_id)

        # Add transaction to history
        db.execute("INSERT INTO history(buyer_id, type, stock, price, shares, time) VALUES(?, ?, ?, ?, ?, strftime('%d/%m/%Y | %H:%M', datetime()))",
                   user_id, "SELL", symbol, price, shares)

        # Return to home page
        return redirect("/")
    # GET method
    else:
        # Owned stocks for selection list
        stocks = db.execute("SELECT * FROM purchases WHERE buyer_id = ?", session["user_id"])

        # Check if user came from home page button
        if not request.args.get('symbol'):

            # Regular template
            return render_template("sell.html", stocks=stocks)
        else:

            # Template with selected stock from home page
            return render_template("sell.html", symbol=request.args.get('symbol'), stocks=stocks)
