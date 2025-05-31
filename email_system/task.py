from celery import Celery
from datetime import datetime
import sqlite3
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from dotenv import load_dotenv
import traceback

# Load .env file
load_dotenv()

# Kiểm tra xem môi trường được load đúng chưa
env_vars = {
    'SMTP_SERVER': os.getenv('SMTP_SERVER'),
    'SMTP_PORT': os.getenv('SMTP_PORT'),
    'SMTP_USERNAME': os.getenv('SMTP_USERNAME') or os.getenv('SMTP_USER'),
    'SENDER_EMAIL': os.getenv('SENDER_EMAIL'),
}

print("==== Thông tin cấu hình email ====")
print(f"SMTP Server: {env_vars['SMTP_SERVER']}")
print(f"SMTP Port: {env_vars['SMTP_PORT']}")
print(f"SMTP Username: {env_vars['SMTP_USERNAME']}")
print(f"Sender Email: {env_vars['SENDER_EMAIL']}")
print("===================================")

# Cấu hình Celery
app = Celery('tasks', broker='redis://localhost:6379/0')

# Cấu hình lịch cho Celery Beat - kiểm tra email thường xuyên hơn
app.conf.beat_schedule = {
    'check-scheduled-emails-frequently': {
        'task': 'tasks.check_scheduled_emails',
        'schedule': 5.0,  # 5 giây một lần để gần như thời gian thực
    },
}

@app.task
def check_scheduled_emails():
    """
    Kiểm tra và gửi các email có lịch gửi đã đến hạn
    """
    try:
        conn = sqlite3.connect('emails.db')
        cursor = conn.cursor()
        
        # Lấy thời gian hiện tại theo ISO format
        current_time = datetime.now().isoformat()
        print(f"Kiểm tra email đến hạn gửi tại thời điểm: {current_time}")
        
        # Thêm khoảng thời gian nhỏ (5 giây) để đảm bảo email được gửi kịp thời
        cursor.execute("SELECT strftime('%s', datetime('now')) as now")
        now_timestamp = int(cursor.fetchone()[0])
        future_timestamp = now_timestamp + 5  # 5 giây tới
        future_time = datetime.fromtimestamp(future_timestamp).isoformat()
        
        # Lấy các email đến hạn gửi theo thứ tự ưu tiên
        # Bao gồm cả email sẽ đến hạn trong 5 giây tới
        cursor.execute("""
            SELECT id, priority, scheduled_time 
            FROM emails 
            WHERE scheduled_time IS NOT NULL 
              AND scheduled_time <= ? 
              AND status='pending' 
              AND is_cancelled=0
            ORDER BY 
              CASE priority
                WHEN 'high' THEN 1
                WHEN 'medium' THEN 2
                WHEN 'low' THEN 3
                ELSE 4
              END,
              scheduled_time ASC
        """, (future_time,))
        
        emails = cursor.fetchall()
        conn.close()
        
        # Gửi các email đến hạn
        print(f"Tìm thấy {len(emails)} email cần gửi")
        for email_id, priority, scheduled_time in emails:
            print(f"Đang gửi email theo lịch: ID={email_id}, Priority={priority}, Scheduled={scheduled_time}")
            send_email_task.delay(email_id, priority=priority)
            
    except Exception as e:
        print("Lỗi kiểm tra email theo lịch:", str(e))
        traceback.print_exc()

@app.task
def send_email_task(email_id, priority='medium'):
    """
    Gửi email và cập nhật trạng thái
    """
    conn = None
    try:
        # Lấy thông tin email từ database
        conn = sqlite3.connect('emails.db')
        cursor = conn.cursor()
        cursor.execute("SELECT recipient, subject, body FROM emails WHERE id=? AND is_cancelled=0", (email_id,))
        row = cursor.fetchone()
        
        if not row:
            print(f"Không tìm thấy email ID={email_id} hoặc email đã bị hủy")
            if conn:
                conn.close()
            return
        
        recipient, subject, body = row
        
        # Cập nhật trạng thái sang đang gửi
        cursor.execute("UPDATE emails SET status='sending' WHERE id=?", (email_id,))
        conn.commit()
        
        # Cấu hình SMTP để gửi email
        smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
        smtp_port = int(os.getenv('SMTP_PORT', 587))
        smtp_username = os.getenv('SMTP_USERNAME') or os.getenv('SMTP_USER', '')
        smtp_password = os.getenv('SMTP_PASSWORD', '')
        sender_email = os.getenv('SENDER_EMAIL', smtp_username)
        
        # Debug thông tin SMTP (không hiển thị password)
        print(f"SMTP Config: Server={smtp_server}, Port={smtp_port}, Username={smtp_username}, Sender={sender_email}")
        
        # Tạo nội dung email
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = recipient
        msg['Subject'] = subject
        
        # Thêm thông tin ưu tiên vào header
        if priority == 'high':
            msg['X-Priority'] = '1'
        elif priority == 'low':
            msg['X-Priority'] = '5'
        else:  # medium
            msg['X-Priority'] = '3'
        
        msg.attach(MIMEText(body, 'plain'))
        
        # Gửi email qua SMTP
        try:
            print(f"Đang kết nối đến SMTP server {smtp_server}:{smtp_port}...")
            server = smtplib.SMTP(smtp_server, smtp_port)
            print("Bắt đầu TLS...")
            server.starttls()
            print(f"Đăng nhập với tài khoản {smtp_username}...")
            server.login(smtp_username, smtp_password)
            text = msg.as_string()
            print(f"Gửi email tới {recipient}...")
            server.sendmail(sender_email, recipient, text)
            print("Đóng kết nối SMTP...")
            server.quit()
            
            # Cập nhật trạng thái thành công
            cursor.execute("UPDATE emails SET status='sent' WHERE id=?", (email_id,))
            conn.commit()
            print(f"Email ID={email_id} đã gửi thành công")
        
        except Exception as smtp_error:
            # Cập nhật trạng thái thất bại
            cursor.execute("UPDATE emails SET status='failed' WHERE id=?", (email_id,))
            conn.commit()
            print(f"Lỗi gửi email ID={email_id}: {str(smtp_error)}")
            traceback.print_exc()
        
    except Exception as e:
        print(f"Lỗi xử lý email ID={email_id}: {str(e)}")
        traceback.print_exc()
        # Nếu có lỗi và kết nối database vẫn mở, cập nhật trạng thái thất bại
        if conn:
            try:
                cursor = conn.cursor()
                cursor.execute("UPDATE emails SET status='failed' WHERE id=?", (email_id,))
                conn.commit()
            except:
                pass
    
    finally:
        # Đảm bảo đóng kết nối database trong mọi trường hợp
        if conn:
            conn.close()