from flask import Flask, render_template, request, redirect, url_for, flash
import sqlite3
from datetime import datetime
from tasks import send_email_task, check_scheduled_emails, schedule_email_with_eta
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
            is_cancelled INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            task_id TEXT
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
    # Xử lý resend - lấy dữ liệu từ email cũ
    resend_id = request.args.get('resend')
    email_data = None
    if resend_id:
        conn = sqlite3.connect('emails.db')
        cursor = conn.cursor()
        cursor.execute("SELECT recipient, subject, body, priority, scheduled_time FROM emails WHERE id=?", (resend_id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            email_data = {
                'recipient': row[0],
                'subject': row[1], 
                'body': row[2],
                'priority': row[3],
                'scheduled_time': row[4]
            }
    
    if request.method == 'POST':
        # Lấy resend_id từ form nếu có
        resend_id = request.form.get('resend_id') or request.args.get('resend')
        
        recipient = request.form['recipient']
        subject = request.form['subject']
        body = request.form['body']
        priority = request.form.get('priority', 'medium')
        schedule = request.form.get('schedule', '').strip()
        
        # Xử lý scheduled_time
        scheduled_time = None
        if schedule:
            try:
                # Đảm bảo định dạng ngày giờ đúng
                scheduled_dt = datetime.strptime(schedule, "%Y-%m-%d %H:%M")
                
                # Kiểm tra thời gian trong quá khứ
                now = datetime.now()
                if scheduled_dt < now:
                    flash('Không thể chọn thời gian trong quá khứ.')
                    return render_template('send_email.html', email_data=email_data, is_resend=bool(resend_id))
                
                # Tính khoảng thời gian đến lúc gửi (giây)
                time_diff_seconds = (scheduled_dt - now).total_seconds()
                  # Chuyển về format ISO cho ETA scheduling
                scheduled_time = scheduled_dt.isoformat()
                
            except Exception as e:
                print("Lỗi định dạng ngày giờ:", str(e))
                traceback.print_exc()
                flash('Định dạng ngày giờ không hợp lệ. Vui lòng chọn lại.')
                return render_template('send_email.html', email_data=email_data, is_resend=bool(resend_id))

        # Lưu email vào database
        try:
            conn = sqlite3.connect('emails.db')
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO emails (recipient, subject, body, priority, scheduled_time, is_cancelled) VALUES (?, ?, ?, ?, ?, ?)",
                (recipient, subject, body, priority, scheduled_time, 0)
            )
            email_id = cursor.lastrowid
              # Nếu đây là resend, xóa email cũ failed
            if resend_id:
                cursor.execute("DELETE FROM emails WHERE id=?", (resend_id,))
                print(f"Đã xóa email cũ ID: {resend_id}")
            
            conn.commit()
            conn.close()
            
            # Xử lý gửi email
            if scheduled_time:
                # Sử dụng ETA scheduling để gửi chính xác
                scheduled_dt = datetime.fromisoformat(scheduled_time)
                current_dt = datetime.now()
                time_diff_seconds = (scheduled_dt - current_dt).total_seconds()
                
                if time_diff_seconds <= 10:
                    # Nếu thời gian gửi trong vòng 10 giây, gửi ngay
                    send_email_task.delay(email_id, priority=priority)
                    if resend_id:
                        flash(f'Email đã được gửi lại ngay lập tức (thời gian gửi quá gần: {time_diff_seconds:.1f}s)!', 'success')
                    else:
                        flash(f'Thời gian gửi quá gần ({time_diff_seconds:.1f}s), email đã được gửi ngay!', 'warning')
                else:
                    # Sử dụng ETA scheduling cho thời gian chính xác
                    task_id = schedule_email_with_eta.delay(email_id, scheduled_time)
                    if resend_id:
                        flash(f'Email đã được gửi lại và lên lịch CHÍNH XÁC vào {schedule}!', 'success')
                    else:
                        flash(f'Email đã được lên lịch gửi CHÍNH XÁC vào {schedule} (Task ID: {task_id})', 'success')
            else:
                # Gửi ngay lập tức
                send_email_task.delay(email_id, priority=priority)
                if resend_id:                    flash('Email đã được gửi lại thành công!', 'success')
                else:
                    flash('Email đã được thêm vào hàng đợi gửi ngay!', 'success')
                
            return redirect(url_for('index'))
            
        except Exception as e:
            print("Lỗi ghi database:", str(e))
            traceback.print_exc()
            flash('Có lỗi khi lưu email. Vui lòng thử lại.')
            return render_template('send_email.html', email_data=email_data, is_resend=bool(resend_id))
            
    # GET request - hiển thị form
    return render_template('send_email.html', email_data=email_data, is_resend=bool(resend_id))

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
    # Chuyển hướng đến trang send với tham số resend
    return redirect(url_for('send_email', resend=email_id))

if __name__ == '__main__':
    app.run(debug=True)