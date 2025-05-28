from flask import Flask, render_template, request, redirect, url_for, flash
import sqlite3
from datetime import datetime
from tasks import send_email_task, check_scheduled_emails
import traceback

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

# Chỉ gọi init_db một lần khi khởi động app
init_db()

@app.route('/')
def index():
    conn = sqlite3.connect('emails.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, recipient, subject, status, scheduled_time, priority FROM emails WHERE is_cancelled=0")
    emails = cursor.fetchall()
    conn.close()
    return render_template('inbox.html', emails=emails)

@app.route('/send', methods=['GET', 'POST'])
def send_email():
    if request.method == 'POST':
        recipient = request.form['recipient']
        subject = request.form['subject']
        body = request.form['body']
        priority = request.form.get('priority', 'medium')
        schedule = request.form.get('schedule', '').strip()        # Xử lý scheduled_time
        scheduled_time = None
        if schedule:
            try:
                # Đảm bảo định dạng ngày giờ đúng
                scheduled_dt = datetime.strptime(schedule, "%Y-%m-%d %H:%M")
                
                # Kiểm tra thời gian trong quá khứ
                now = datetime.now()
                if scheduled_dt < now:
                    flash('Không thể chọn thời gian trong quá khứ.')
                    return render_template('send_email.html')
                
                # Tính khoảng thời gian đến lúc gửi (giây)
                time_diff_seconds = (scheduled_dt - now).total_seconds()
                
                # Nếu thời gian gửi gần kề (< 30 giây), đánh dấu để gửi ngay lập tức
                if time_diff_seconds < 30:
                    scheduled_time = None  # Sẽ gửi ngay lập tức
                    flash(f'Thời gian gửi quá gần, email sẽ được gửi ngay lập tức!')
                else:
                    # Chuyển về format ISO
                    scheduled_time = scheduled_dt.isoformat()
                
            except Exception as e:
                print("Lỗi định dạng ngày giờ:", str(e))
                traceback.print_exc()
                flash('Định dạng ngày giờ không hợp lệ. Vui lòng chọn lại.')
                return render_template('send_email.html')

        # Lưu email vào database
        try:
            conn = sqlite3.connect('emails.db')
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO emails (recipient, subject, body, priority, scheduled_time, is_cancelled) VALUES (?, ?, ?, ?, ?, ?)",
                (recipient, subject, body, priority, scheduled_time, 0)
            )
            email_id = cursor.lastrowid
            conn.commit()
            conn.close()
              # Xử lý gửi email
            if scheduled_time:
                # Tính thời gian còn lại đến lúc gửi
                time_diff = (datetime.strptime(schedule, "%Y-%m-%d %H:%M") - datetime.now()).total_seconds()
                
                if time_diff <= 60:  # Nếu thời gian gửi trong vòng 1 phút
                    # Kích hoạt task kiểm tra ngay lập tức để gửi email nhanh hơn
                    check_scheduled_emails.delay()
                    flash(f'Email đã được lên lịch gửi vào {schedule} (sẽ được kiểm tra ngay lập tức).')
                else:
                    flash(f'Email đã được lên lịch gửi vào {schedule}.')
            else:
                send_email_task.delay(email_id, priority=priority)
                flash('Đã thêm email vào hàng đợi gửi.')
                
            return redirect(url_for('index'))
            
        except Exception as e:
            print("Lỗi ghi database:", str(e))
            traceback.print_exc()
            flash('Có lỗi khi lưu email. Vui lòng thử lại.')
            return render_template('send_email.html')
            
    # GET request - hiển thị form
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
    conn = sqlite3.connect('emails.db')
    cursor = conn.cursor()
    cursor.execute("SELECT priority FROM emails WHERE id=?", (email_id,))
    row = cursor.fetchone()
    priority = row[0] if row else 'medium'
    conn.close()
    
    send_email_task.delay(email_id, priority=priority)
    flash('Đã gửi lại email.')
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)