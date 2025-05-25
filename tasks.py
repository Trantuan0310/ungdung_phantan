from celery import Celery
import sqlite3
import smtplib
from email.mime.text import MIMEText
from dotenv import load_dotenv
import os

# Tải biến môi trường
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '.env'))

# Cấu hình Celery
app = Celery('email_system',
             broker='redis://localhost:6379/0',
             backend='redis://localhost:6379/0')

app.conf.update(
    result_expires=3600,
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
)

# Thông tin SMTP từ biến môi trường
SMTP_SERVER = 'smtp.gmail.com'
SMTP_PORT = 587
SMTP_USER = os.getenv('SMTP_USER')  # Email của bạn
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD')  # App Password

@app.task
def send_email_task(email_id, priority='medium'):
    # Kết nối cơ sở dữ liệu SQLite
    conn = sqlite3.connect('emails.db')
    cursor = conn.cursor()
    cursor.execute("SELECT recipient, subject, body FROM emails WHERE id=?", (email_id,))
    email = cursor.fetchone()
    conn.close()

    if email:
        recipient, subject, body = email
        # Tạo email
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = SMTP_USER
        msg['To'] = recipient

        try:
            # Kết nối và gửi email qua SMTP
            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
                server.starttls()  # Bật TLS để bảo mật
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.sendmail(SMTP_USER, recipient, msg.as_string())
            # Cập nhật trạng thái email
            conn = sqlite3.connect('emails.db')
            cursor = conn.cursor()
            cursor.execute("UPDATE emails SET status='sent' WHERE id=?", (email_id,))
            conn.commit()
            conn.close()
            print(f"Email sent successfully to {recipient}")
        except Exception as e:
            # Ghi lỗi nếu gửi thất bại
            print(f"Error sending email: {str(e)}")
            conn = sqlite3.connect('emails.db')
            cursor = conn.cursor()
            cursor.execute("UPDATE emails SET status='failed' WHERE id=?", (email_id,))
            conn.commit()
            conn.close()
            raise e

# Task kiểm tra email lập lịch
@app.task
def check_scheduled_emails():
    import sqlite3
    from datetime import datetime

    conn = sqlite3.connect('emails.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, recipient, subject, body FROM emails WHERE scheduled_time <= ? AND status='pending' AND is_cancelled=0", (datetime.utcnow().isoformat(),))
    emails = cursor.fetchall()
    conn.close()

    for email in emails:
        email_id = email[0]
        send_email_task.delay(email_id)