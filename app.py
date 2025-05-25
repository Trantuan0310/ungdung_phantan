from flask import Flask, render_template, request, redirect, url_for, flash
import sqlite3
from datetime import datetime, timedelta
from tasks import send_email_task, check_scheduled_emails

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Để sử dụng flash message

# Khởi tạo cơ sở dữ liệu SQLite
def init_db():
    conn = sqlite3.connect('emails.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS emails (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recipient TEXT NOT NULL,
            subject TEXT NOT NULL,
            body TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            priority TEXT DEFAULT 'medium',
            scheduled_time TEXT,
            is_cancelled INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()

init_db()

@app.route('/')
def index():
    conn = sqlite3.connect('emails.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, recipient, subject, status, scheduled_time FROM emails WHERE is_cancelled=0")
    emails = cursor.fetchall()
    conn.close()
    return render_template('inbox.html', emails=emails)

@app.route('/send', methods=['GET', 'POST'])
def send_email():
    if request.method == 'POST':
        recipient = request.form['recipient']
        subject = request.form['subject']
        body = request.form['body']
        priority = request.form['priority']
        schedule = request.form.get('schedule', '')

        conn = sqlite3.connect('emails.db')
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO emails (recipient, subject, body, priority, scheduled_time, is_cancelled) VALUES (?, ?, ?, ?, ?, ?)",
            (recipient, subject, body, priority, schedule or None, 0)
        )
        email_id = cursor.lastrowid
        conn.commit()
        conn.close()

        if schedule:
            check_scheduled_emails.delay()
        else:
            send_email_task.delay(email_id, priority=priority)
        flash('Đã thêm email vào hàng đợi gửi.')
        return redirect(url_for('index'))
    return render_template('send_email.html')

@app.route('/cancel/<int:email_id>')
def cancel_email(email_id):
    conn = sqlite3.connect('emails.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE emails SET is_cancelled=1, status='cancelled' WHERE id=?", (email_id,))
    conn.commit()
    conn.close()
    flash('Đã hủy email.')
    return redirect(url_for('index'))

@app.route('/email/<int:email_id>')
def view_email(email_id):
    conn = sqlite3.connect('emails.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM emails WHERE id=?", (email_id,))
    email = cursor.fetchone()
    conn.close()
    return render_template('view_email.html', email=email)

@app.route('/email/<int:email_id>/delete')
def delete_email(email_id):
    conn = sqlite3.connect('emails.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM emails WHERE id=?", (email_id,))
    conn.commit()
    conn.close()
    flash('Đã xóa email.')
    return redirect(url_for('index'))

@app.route('/email/<int:email_id>/resend')
def resend_email(email_id):
    send_email_task.delay(email_id)
    flash('Đã gửi lại email.')
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)