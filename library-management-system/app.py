from flask import Flask, render_template, request, redirect, url_for, flash, session
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
import re
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = "super_secret_key_change_this"

DB_NAME = "library.db"

# ---------------- VALIDATIONS ----------------
def is_strong_password(password):
    return len(password) >= 8 and re.search(r"[A-Z]", password)

def is_valid_phone(phone):
    return phone.isdigit() and len(phone) == 10

def is_valid_email(email):
    return "@" in email and "." in email

# ---------------- DATABASE ----------------
def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = sqlite3.connect('library.db')
    cursor = conn.cursor()

    # Members table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS members (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        MEMBER_ID TEXT UNIQUE,
        NAME TEXT,
        EMAIL TEXT,
        PHONE TEXT,
        PASSWORD TEXT
    )
    """)

    # Books table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS books (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        book_id TEXT UNIQUE,
        title TEXT,
        author TEXT,
        category TEXT,
        quantity INTEGER DEFAULT 1
    )
    """)

    # Transactions table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        book_id TEXT,
        member_id TEXT,
        action TEXT,
        issue_date TEXT,
        due_date TEXT,
        return_date TEXT,
        fine INTEGER DEFAULT 0
    )
    """)

    # Default admin
    cursor.execute("SELECT * FROM members WHERE NAME='admin'")
    admin = cursor.fetchone()

    if not admin:
        cursor.execute("""
        INSERT INTO members (MEMBER_ID, NAME, EMAIL, PHONE, PASSWORD)
        VALUES (?, ?, ?, ?, ?)
        """, (
            "000",
            "admin",
            "admin@gmail.com",
            "9999999999",
            generate_password_hash("admin123")
        ))

    conn.commit()
    conn.close()
# ---------------- AUTH ----------------
def is_logged_in():
    return "user" in session

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        name = request.form.get("username")
        password = request.form.get("password")

        conn = sqlite3.connect('library.db')
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM members WHERE NAME=?", (name,))
        member = cursor.fetchone()
        conn.close()

        if member and member[5] and check_password_hash(member[5], password):
            session["user"] = name
            session["member_id"] = member[1]  # store MEMBER_ID

            # ✅ ROLE BASED REDIRECT
            if name.lower() == "admin":
                return redirect('/dashboard')
            else:
                return redirect('/user_billing')

        flash("Invalid username or password!", "danger")
        return redirect('/login')

    return render_template('login.html')

#-----------------User Billing-------------

@app.route("/user_billing")
def user_billing():
    if not is_logged_in():
        return redirect(url_for("login"))

    # ❌ Prevent admin access
    if session.get("user").lower() == "admin":
        return redirect('/dashboard')

    member_id = session.get("member_id")

    conn = get_db_connection()

    # ✅ ALL BOOKS
    books = conn.execute("SELECT * FROM books").fetchall()

    # ✅ CURRENTLY BORROWED BOOKS
    borrowed = conn.execute("""
        SELECT * FROM transactions
        WHERE member_id=? AND action='Issued' AND return_date IS NULL
    """, (member_id,)).fetchall()

    # ✅ HISTORY
    history = conn.execute("""
        SELECT * FROM transactions
        WHERE member_id=?
        ORDER BY id DESC
    """, (member_id,)).fetchall()

    conn.close()

    return render_template(
        "user_billing.html",
        books=books,
        borrowed=borrowed,
        history=history
    )
# ---------------- DASHBOARD ----------------
@app.route("/")
@app.route("/dashboard")
def dashboard():
    if not is_logged_in():
        return redirect(url_for("login"))
    
     # ❌ Block normal users
    if session.get("user").lower() != "admin":
        return redirect('/user_billing')

    conn = get_db_connection()

    total_books = conn.execute("SELECT SUM(quantity) FROM books").fetchone()[0] or 0
    available_books = conn.execute("SELECT SUM(quantity) FROM books").fetchone()[0] or 0
    total_members = conn.execute("SELECT COUNT(*) FROM members").fetchone()[0]
    total_transactions = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]

    conn.close()

    return render_template("dashboard.html",
        total_books=total_books,
        available_books=available_books,
        issued_books=total_transactions,
        total_members=total_members,
        total_transactions=total_transactions
    )

# ---------------- BOOKS ----------------
@app.route("/books")
def books():
    if not is_logged_in():
        return redirect(url_for("login"))

    search = request.args.get("search", "").strip()
    conn = get_db_connection()

    if search:
        books = conn.execute("""
            SELECT * FROM books
            WHERE title LIKE ? OR author LIKE ? OR book_id LIKE ? OR category LIKE ?
        """, (f"%{search}%",)*4).fetchall()
    else:
        books = conn.execute("SELECT * FROM books ORDER BY id DESC").fetchall()

    books = [dict(book) for book in books]

    for book in books:
        book['status'] = "Available" if book['quantity'] > 0 else "Out of Stock"

    conn.close()
    return render_template("books.html", books=books, search=search)

@app.route('/add_book', methods=['POST'])
def add_book():
    title = request.form.get("title")
    author = request.form.get("author")
    book_id = request.form.get("book_id")
    category = request.form.get("category")
    quantity = int(request.form.get("quantity"))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT quantity FROM books WHERE title=?", (title,))
    existing = cursor.fetchone()

    if existing:
        cursor.execute("UPDATE books SET quantity = quantity + ? WHERE title=?", (quantity, title))
        flash("Quantity updated!", "success")
    else:
        cursor.execute("""
        INSERT INTO books (book_id, title, author, category, quantity)
        VALUES (?, ?, ?, ?, ?)
        """, (book_id, title, author, category, quantity))
        flash("Book added!", "success")

    conn.commit()
    conn.close()
    return redirect('/books')

@app.route("/delete_book/<book_id>")
def delete_book(book_id):
    conn = get_db_connection()
    conn.execute("DELETE FROM books WHERE book_id=?", (book_id,))
    conn.commit()
    conn.close()
    flash("Book deleted!", "success")
    return redirect(url_for("books"))

# ---------------- MEMBERS ----------------
@app.route("/members")
def members():
    conn = get_db_connection()
    members = conn.execute("SELECT * FROM members ORDER BY id DESC").fetchall()
    conn.close()
    return render_template("members.html", members=members)

@app.route('/add_member', methods=['POST'])
def add_member():
    name = request.form.get('name')
    member_id = request.form.get('member_id')

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM members WHERE MEMBER_ID=?", (member_id,))
    if cursor.fetchone():
        flash("Member ID exists!", "danger")
        return redirect('/members')

    cursor.execute("INSERT INTO members (MEMBER_ID, NAME) VALUES (?, ?)", (member_id, name))
    conn.commit()
    conn.close()

    flash("Member added!", "success")
    return redirect('/members')

# ---------------- ISSUE BOOK ----------------
@app.route("/issue_book", methods=["POST"])
def issue_book():
    if not is_logged_in():
        return redirect(url_for("login"))

    book_id = request.form["book_id"]
    member_id = request.form["member_id"]

    conn = get_db_connection()

    book = conn.execute("SELECT * FROM books WHERE book_id=?", (book_id,)).fetchone()

    if not book or book["quantity"] <= 0:
        flash("Book not available!", "danger")
        conn.close()
        return redirect('/transactions')

    # ✅ Reduce quantity
    conn.execute("UPDATE books SET quantity = quantity - 1 WHERE book_id=?", (book_id,))

    # ✅ ADD TRANSACTION RECORD
    issue_date = datetime.now()
    due_date = issue_date + timedelta(days=14)

    conn.execute("""
        INSERT INTO transactions (book_id, member_id, action, issue_date, due_date)
        VALUES (?, ?, ?, ?, ?)
    """, (
        book_id,
        member_id,
        "Issued",
        issue_date.strftime("%Y-%m-%d"),
        due_date.strftime("%Y-%m-%d")
    ))

    conn.commit()
    conn.close()

    flash("Book issued successfully!", "success")
    return redirect('/transactions')

# ---------------- RETURN BOOK ----------------
@app.route("/return_book", methods=["POST"])
def return_book():
    if not is_logged_in():
        return redirect(url_for("login"))

    book_id = request.form.get("book_id").strip()
    member_id = request.form.get("member_id").strip()

    conn = get_db_connection()

    # ✅ 1. CHECK BOOK + MEMBER
    book = conn.execute("SELECT * FROM books WHERE book_id=?", (book_id,)).fetchone()
    member = conn.execute("SELECT * FROM members WHERE MEMBER_ID=?", (member_id,)).fetchone()

    if not book or not member:
        flash("❌ Details not found!", "danger")
        conn.close()
        return redirect('/transactions')

    # ✅ 2. FIND ACTIVE ISSUE ONLY (IMPORTANT)
    txn = conn.execute("""
        SELECT * FROM transactions
        WHERE book_id=? AND member_id=? 
        AND action='Issued' 
        AND return_date IS NULL
        ORDER BY id DESC LIMIT 1
    """, (book_id, member_id)).fetchone()

    if not txn:
        flash("❌ No active borrowed record found!", "danger")
        conn.close()
        return redirect('/transactions')

    # ✅ 3. CALCULATE FINE
    return_date = datetime.now()
    due_date = datetime.strptime(txn["due_date"], "%Y-%m-%d")

    late_days = (return_date.date() - due_date.date()).days
    fine = late_days * 5 if late_days > 0 else 0

    # ✅ 4. MARK ISSUE AS RETURNED (KEY FIX)
    conn.execute("""
        UPDATE transactions
        SET return_date=?, fine=?
        WHERE id=?
    """, (
        return_date.strftime("%Y-%m-%d"),
        fine,
        txn["id"]
    ))

    # ❌ REMOVE THIS (VERY IMPORTANT)
    # DO NOT INSERT A NEW "Returned" ROW

    # ✅ 5. UPDATE QUANTITY
    conn.execute(
        "UPDATE books SET quantity = quantity + 1 WHERE book_id=?",
        (book_id,)
    )

    conn.commit()
    conn.close()

    if fine > 0:
        flash(f"Book returned! Fine: ₹{fine}", "success")
    else:
        flash("Book returned successfully!", "success")

    return redirect('/transactions')
# ---------------- REGISTER ----------------
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        member_id = request.form.get("member_id")
        name = request.form.get("name")
        email = request.form.get("email")
        phone = request.form.get("phone")
        password = request.form.get("password")

        if not is_valid_phone(phone):
            flash("Phone must be 10 digits", "danger")
            return redirect('/register')

        if not is_valid_email(email):
            flash("Invalid email", "danger")
            return redirect('/register')

        if not is_strong_password(password):
            flash("Weak password", "danger")
            return redirect('/register')

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM members WHERE MEMBER_ID=? AND NAME=?", (member_id, name))
        member = cursor.fetchone()

        if not member:
            flash("Contact admin first", "danger")
            return redirect('/register')

        hashed = generate_password_hash(password)

        cursor.execute("""
        UPDATE members SET EMAIL=?, PHONE=?, PASSWORD=?
        WHERE MEMBER_ID=? AND NAME=?
        """, (email, phone, hashed, member_id, name))

        conn.commit()
        conn.close()

        flash("Registered successfully!", "success")
        return redirect('/login')

    return render_template('register.html')

# ---------------- TRANSACTIONS ----------------
@app.route("/transactions")
def transactions():
    if not is_logged_in():
        return redirect(url_for("login"))

    conn = get_db_connection()

    transactions = conn.execute("""
        SELECT * FROM transactions
        ORDER BY id DESC
    """).fetchall()

    conn.close()

    return render_template("transactions.html", transactions=transactions)

#--------------Logout-------------------------
@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully!", "success")
    return redirect(url_for("login"))
    return render_template("transactions.html", transactions=transactions)
# ---------------- MAIN ----------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
