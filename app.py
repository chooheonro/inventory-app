from flask import Flask, render_template, request, redirect, session, send_file
import sqlite3
import datetime
import pandas as pd

app = Flask(__name__)
app.secret_key = 'inventory_secret_key'
DB_NAME = 'inventory.db'


def get_db():
    return sqlite3.connect(DB_NAME)


def init_db():
    conn = get_db()
    c = conn.cursor()

    c.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT
    )
    ''')

    c.execute('''
    CREATE TABLE IF NOT EXISTS items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        barcode TEXT,
        name TEXT,
        price INTEGER DEFAULT 0,
        vendor TEXT,
        stock INTEGER DEFAULT 0,
        min_stock INTEGER DEFAULT 0
    )
    ''')

    c.execute('''
    CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        item_id INTEGER,
        barcode TEXT,
        item_name TEXT,
        type TEXT,
        qty INTEGER,
        user TEXT,
        date TEXT
    )
    ''')

    c.execute("INSERT OR IGNORE INTO users (username, password) VALUES ('admin', '1234')")

    for sql in [
        "ALTER TABLE items ADD COLUMN barcode TEXT",
        "ALTER TABLE logs ADD COLUMN barcode TEXT"
    ]:
        try:
            c.execute(sql)
        except:
            pass

    conn.commit()
    conn.close()


init_db()


def login_required():
    return 'user' in session


@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db()
        user = conn.execute(
            "SELECT * FROM users WHERE username=? AND password=?",
            (username, password)
        ).fetchone()
        conn.close()

        if user:
            session['user'] = username
            return redirect('/main')

        return render_template('login.html', error='아이디 또는 비밀번호가 틀렸습니다.')

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')


@app.route('/main')
def main():
    if not login_required():
        return redirect('/')

    keyword = request.args.get('keyword', '')

    conn = get_db()
    if keyword:
        items = conn.execute(
            '''
            SELECT * FROM items
            WHERE name LIKE ? OR vendor LIKE ? OR barcode LIKE ?
            ORDER BY id DESC
            ''',
            (f'%{keyword}%', f'%{keyword}%', f'%{keyword}%')
        ).fetchall()
    else:
        items = conn.execute("SELECT * FROM items ORDER BY id DESC").fetchall()
    conn.close()

    return render_template('index.html', items=items, keyword=keyword)


@app.route('/add', methods=['POST'])
def add():
    if not login_required():
        return redirect('/')

    barcode = request.form.get('barcode', '')
    name = request.form['name']
    price = int(request.form.get('price') or 0)
    vendor = request.form.get('vendor', '')
    min_stock = int(request.form.get('min_stock') or 0)

    conn = get_db()
    conn.execute(
        "INSERT INTO items (barcode, name, price, vendor, stock, min_stock) VALUES (?, ?, ?, ?, 0, ?)",
        (barcode, name, price, vendor, min_stock)
    )
    conn.commit()
    conn.close()

    return redirect('/main')


@app.route('/edit/<int:item_id>', methods=['POST'])
def edit(item_id):
    if not login_required():
        return redirect('/')

    barcode = request.form.get('barcode', '')
    name = request.form['name']
    price = int(request.form.get('price') or 0)
    vendor = request.form.get('vendor', '')
    min_stock = int(request.form.get('min_stock') or 0)

    conn = get_db()
    conn.execute(
        "UPDATE items SET barcode=?, name=?, price=?, vendor=?, min_stock=? WHERE id=?",
        (barcode, name, price, vendor, min_stock, item_id)
    )
    conn.commit()
    conn.close()

    return redirect('/main')


@app.route('/delete/<int:item_id>')
def delete(item_id):
    if not login_required():
        return redirect('/')

    conn = get_db()
    conn.execute("DELETE FROM items WHERE id=?", (item_id,))
    conn.commit()
    conn.close()

    return redirect('/main')


@app.route('/in', methods=['POST'])
def stock_in():
    if not login_required():
        return redirect('/')

    item_id = request.form['id']
    qty = int(request.form['qty'])
    user = session['user']
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    conn = get_db()
    item = conn.execute("SELECT barcode, name FROM items WHERE id=?", (item_id,)).fetchone()

    if item:
        barcode, item_name = item
        conn.execute("UPDATE items SET stock = stock + ? WHERE id=?", (qty, item_id))
        conn.execute(
            "INSERT INTO logs (item_id, barcode, item_name, type, qty, user, date) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (item_id, barcode, item_name, '입고', qty, user, now)
        )

    conn.commit()
    conn.close()

    return redirect('/main')


@app.route('/out', methods=['POST'])
def stock_out():
    if not login_required():
        return redirect('/')

    item_id = request.form['id']
    qty = int(request.form['qty'])
    user = session['user']
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    conn = get_db()
    item = conn.execute("SELECT barcode, name, stock FROM items WHERE id=?", (item_id,)).fetchone()

    if item:
        barcode, item_name, current_stock = item

        if qty > current_stock:
            conn.close()
            return redirect('/main?error=stock')

        conn.execute("UPDATE items SET stock = stock - ? WHERE id=?", (qty, item_id))
        conn.execute(
            "INSERT INTO logs (item_id, barcode, item_name, type, qty, user, date) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (item_id, barcode, item_name, '출고', qty, user, now)
        )

    conn.commit()
    conn.close()

    return redirect('/main')


@app.route('/barcode_inout', methods=['POST'])
def barcode_inout():
    if not login_required():
        return redirect('/')

    barcode = request.form['barcode']
    qty = int(request.form['qty'])
    action = request.form['action']
    user = session['user']
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    conn = get_db()
    item = conn.execute("SELECT id, name, stock FROM items WHERE barcode=?", (barcode,)).fetchone()

    if not item:
        conn.close()
        return redirect('/main?error=barcode')

    item_id, item_name, stock = item

    if action == '입고':
        conn.execute("UPDATE items SET stock = stock + ? WHERE id=?", (qty, item_id))
    else:
        if qty > stock:
            conn.close()
            return redirect('/main?error=stock')
        conn.execute("UPDATE items SET stock = stock - ? WHERE id=?", (qty, item_id))

    conn.execute(
        "INSERT INTO logs (item_id, barcode, item_name, type, qty, user, date) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (item_id, barcode, item_name, action, qty, user, now)
    )

    conn.commit()
    conn.close()

    return redirect('/main')


@app.route('/logs')
def logs():
    if not login_required():
        return redirect('/')

    conn = get_db()
    logs = conn.execute("SELECT * FROM logs ORDER BY id DESC").fetchall()
    conn.close()

    return render_template('logs.html', logs=logs)


@app.route('/low_stock')
def low_stock():
    if not login_required():
        return redirect('/')

    conn = get_db()
    items = conn.execute(
        "SELECT * FROM items WHERE stock <= min_stock ORDER BY stock ASC"
    ).fetchall()
    conn.close()

    return render_template('low_stock.html', items=items)


@app.route('/stats')
def stats():
    if not login_required():
        return redirect('/')

    conn = get_db()

    total_items = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    total_stock = conn.execute("SELECT IFNULL(SUM(stock), 0) FROM items").fetchone()[0]
    total_value = conn.execute("SELECT IFNULL(SUM(price * stock), 0) FROM items").fetchone()[0]
    low_count = conn.execute("SELECT COUNT(*) FROM items WHERE stock <= min_stock").fetchone()[0]

    top_out = conn.execute('''
        SELECT item_name, SUM(qty) AS total_qty
        FROM logs
        WHERE type='출고'
        GROUP BY item_name
        ORDER BY total_qty DESC
        LIMIT 10
    ''').fetchall()

    conn.close()

    return render_template(
        'stats.html',
        total_items=total_items,
        total_stock=total_stock,
        total_value=total_value,
        low_count=low_count,
        top_out=top_out
    )


@app.route('/users', methods=['GET', 'POST'])
def users():
    if not login_required():
        return redirect('/')

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db()
        try:
            conn.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password))
            conn.commit()
        except:
            pass
        conn.close()

        return redirect('/users')

    conn = get_db()
    users = conn.execute("SELECT id, username FROM users ORDER BY id DESC").fetchall()
    conn.close()

    return render_template('users.html', users=users)


@app.route('/change_password', methods=['GET', 'POST'])
def change_password():
    if not login_required():
        return redirect('/')

    if request.method == 'POST':
        old_pw = request.form['old_password']
        new_pw = request.form['new_password']
        username = session['user']

        conn = get_db()
        user = conn.execute(
            "SELECT * FROM users WHERE username=? AND password=?",
            (username, old_pw)
        ).fetchone()

        if user:
            conn.execute("UPDATE users SET password=? WHERE username=?", (new_pw, username))
            conn.commit()
            conn.close()
            return render_template('change_password.html', message='비밀번호가 변경되었습니다.')

        conn.close()
        return render_template('change_password.html', error='기존 비밀번호가 틀렸습니다.')

    return render_template('change_password.html')


@app.route('/excel')
def excel():
    if not login_required():
        return redirect('/')

    conn = get_db()
    df = pd.read_sql_query("""
        SELECT 
            barcode AS 바코드,
            name AS 품목명,
            price AS 단가,
            vendor AS 거래처,
            stock AS 현재재고,
            min_stock AS 최소재고
        FROM items
    """, conn)
    conn.close()

    file_name = '재고현황.xlsx'
    df.to_excel(file_name, index=False)

    return send_file(file_name, as_attachment=True)


app.run(host='0.0.0.0', port=8000)