from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session, url_for
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


#Index - Return table with stocks in user's portfolio
@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    #select user's portfolio
    rows = db.execute("SELECT * FROM portfolio WHERE userid=:id", id=session["user_id"])

    #set temporary holding place for cash to zero
    tcash = 0

   #update the stock information in user's portfolio
    for row in rows:
        stock = row["stock"]
        number = row["number"]
        quote = lookup(stock)
        total = float(number) * float(quote["price"])
        tcash += total
        db.execute("UPDATE portfolio SET price=:price, total=:total WHERE userid=:id AND stock=:stock AND number=:number", price=usd(quote["price"]), total=total, id=session["user_id"], stock=stock, number=number)

    #select user's cash and updated portfolio
    updated_cash = db.execute("SELECT cash FROM users WHERE id=:id", id=session["user_id"])
    tcash += updated_cash[0]["cash"]
    updated_stock = db.execute("SELECT stock, SUM(number) AS number, price, SUM(total) AS stock_total FROM portfolio WHERE userid=:id GROUP BY stock HAVING SUM(number) > 0", id=session["user_id"])

    return render_template("index.html", stocks=updated_stock, cash=usd(updated_cash[0]["cash"]), all_total=usd(tcash))

@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":

        #validate input
        try:
            shares = int(request.form.get("shares"))
            stock = lookup(request.form.get("symbol"))
        except:
            return apology("enter a valid ticker")

        #check shares not blank
        if not stock:
            return apology("please enter a stock")

        #are shares there and more than 0?
        if not shares or shares <= 0:
            return apology("Please fill in all fields")

        #does the user have enough cash
        money = db.execute("SELECT cash FROM users WHERE id=:id", id=session["user_id"])
        money = int(money[0]['cash'])
        if stock["price"] * shares > money:
            return apology("You don't have enough money")
        else:
            db.execute("INSERT INTO portfolio (stock, price, trans_price, number, userid) VALUES (:stock, :price, :trans_price, :number, :userid)", stock=stock['symbol'], price=stock['price'], trans_price=usd(stock['price']), number=shares, userid=session["user_id"])
            db.execute("UPDATE users SET cash=cash-:total WHERE id=:userid", total=(stock['price'] * shares), userid=session["user_id"])

            return redirect("/")

    if request.method == "GET":
        return render_template("buy.html")

@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    
    #select user's portfolio
    rows = db.execute("SELECT stock, number, trans_price, transaction_stamp FROM portfolio WHERE userid=:id", id=session["user_id"])
    return render_template("history.html", rows=rows)

@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    #forget any user_id
    session.clear()

    #user reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        #ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        #ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        #query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        #ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        #remember which user has logged in
        session["user_id"] = rows[0]["id"]

        #redirect user to home page
        return redirect("/")

    #user reached route via GET (as by clicking a link or via redirect)
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
    
    #lookup stock's price and return another page
    if request.method == "POST":
        s = lookup(request.form.get("symbol"))
        if s != None:
            return render_template("quoted.html", stock = s)
        else:
            return apology("Please enter a valid ticker")
    if request.method == "GET":
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    if request.method == "POST":
        #check not blank
        if request.form.get("username") == "" or request.form.get("password") == "" or request.form.get("confirmation") == "":
            return apology("Please fill in all fields")

        #check pws match
        if request.form.get("password") != request.form.get("confirmation"):
            return apology("Oops, we don't know which you prefer. Please make your password and confirmation match.")

        #hash the user's pw
        hash = generate_password_hash(request.form.get("password"))

        #check for unique username
        result = db.execute("INSERT INTO users (username, hash) VALUES (:username, :hash)", username=request.form.get("username"), hash=hash)
        if not result:
            return apology("Sorry, we already have a user registered as such. Did you mean to login?", 400)

         #remember which user has logged in
        session["user_id"] = ["id"]

        return render_template("register.html")

    #user reached route via GET
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "POST":

        #test for selection of stocks
        if request.form.get("symbol") == "" or request.form.get("shares") == "":
            return apology("Please fill in all fields")

        #test for positive integer
        if str.isdigit(request.form.get("shares")) == False:
            return apology("Please select a positive number of shares")

        # does the user have enough shares of that stock
        user_stock = request.form.get("symbol")
        user_number = int(request.form.get("shares"))
        owned = db.execute("SELECT SUM(number) FROM portfolio WHERE userid=:id AND stock=:stock", stock = user_stock, id=session["user_id"])
        owned = int(owned[0]['SUM(number)'])
        if user_number > owned:
            return apology("You don't have enough shares")

        #in the portfolio table, add a negative to the number field of the purchased stock
        #in the cash table, lookup the current price and add the cash to the user's cash balanace
        else:
            pay = lookup(request.form.get("symbol"))
            user_number = int(request.form.get("shares"))
            db.execute("UPDATE users SET cash=cash+:total WHERE id=:userid", total=(pay['price'] * user_number), userid=session["user_id"])

            user_number = int(request.form.get("shares")) * -1
            db.execute("INSERT INTO portfolio (stock, number, price, trans_price, userid) VALUES (:stock, :number, :price, :trans_price, :userid)", stock=user_stock, number=user_number, price=(pay['price'] * user_number), trans_price=usd(pay['price']), userid=session["user_id"])

            user_id=session["user_id"]
            return redirect(url_for('index'))

    if request.method == "GET":
        #get stocks from portfolio and return to html form
        stocks = db.execute("SELECT stock FROM portfolio WHERE userid=:id GROUP BY stock", id=session["user_id"])
        return render_template("sell.html", stocks=stocks)

def errorhandler(e):
    """Handle error"""
    return apology(e.name, e.code)

# listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)