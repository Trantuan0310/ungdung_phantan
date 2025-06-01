from celery import Celery
from datetime import datetime, timedelta
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

# Cấu hình lịch cho Celery Beat - chỉ làm backup check
app.conf.beat_schedule = {
    'check-scheduled-emails-backup': {
        'task': 'tasks.check_scheduled_emails',
        'schedule': 30.0,  # Giảm xuống mỗi 30s làm backup thôi
    },
}

@app.task
def check_scheduled_emails():
    """
    Kiểm tra các email có lịch gửi đã đến hạn (backup cho ETA tasks)
    Chỉ xử lý những email chưa được schedule bằng ETA
    """
    try:
        conn = sqlite3.connect('emails.db')
        cursor = conn.cursor()
        
        # Lấy thời gian hiện tại theo ISO format
        current_time = datetime.now().isoformat()
        print(f"🔄 [BACKUP CHECK] Kiểm tra email backup tại: {current_time}")
        
        # Chỉ lấy email pending (chưa được ETA schedule) và đã đến hạn
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
        """, (current_time,))
        
        emails = cursor.fetchall()
        conn.close()
        
        if emails:
            print(f"🚨 [BACKUP] Tìm thấy {len(emails)} email bị miss bởi ETA, gửi ngay:")
            for email_id, priority, scheduled_time in emails:
                print(f"  📧 Email ID={email_id}, Priority={priority}, Scheduled={scheduled_time}")
                send_email_task.delay(email_id, priority=priority)
        else:
            print(f"✅ [BACKUP] Không có email nào bị miss")
            
    except Exception as e:
        error_time = datetime.now().isoformat()
        print(f"[{error_time}] ❌ LỖI backup check: {str(e)}")
        traceback.print_exc()

@app.task
def send_email_task(email_id, priority='medium'):
    """
    Gửi email và cập nhật trạng thái
    """
    conn = None
    start_time = datetime.now()
    print(f"📧 [{start_time.isoformat()}] BẮT ĐẦU GỬI EMAIL ID={email_id}, Priority={priority.upper()}")
    
    try:
        # Lấy thông tin email từ database
        conn = sqlite3.connect('emails.db')
        cursor = conn.cursor()
        cursor.execute("SELECT recipient, subject, body, scheduled_time FROM emails WHERE id=? AND is_cancelled=0", (email_id,))
        row = cursor.fetchone()
        
        if not row:
            print(f"❌ Không tìm thấy email ID={email_id} hoặc email đã bị hủy")
            if conn:
                conn.close()
            return
        
        recipient, subject, body, scheduled_time = row
        
        # Kiểm tra xem có đúng thời gian không (cho ETA tasks)
        if scheduled_time:
            scheduled_dt = datetime.fromisoformat(scheduled_time)
            current_dt = datetime.now()
            time_diff = abs((current_dt - scheduled_dt).total_seconds())
            
            if time_diff > 2:  # Cho phép sai lệch 2 giây
                print(f"⚠️  Email ID={email_id} gửi muộn {time_diff:.1f}s (scheduled: {scheduled_time})")
            else:
                print(f"✅ Email ID={email_id} gửi đúng thời gian (sai lệch: {time_diff:.1f}s)")
        
        print(f"📋 Thông tin: To={recipient}, Subject='{subject}'")
        
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

@app.task
def schedule_email_with_eta(email_id, scheduled_time_str):
    """
    Lên lịch gửi email với ETA chính xác (không delay)
    """
    try:
        scheduled_time = datetime.fromisoformat(scheduled_time_str)
        current_time = datetime.now()
        
        print(f"📅 SCHEDULE EMAIL ID={email_id} cho {scheduled_time.isoformat()}")
        print(f"⏰ Thời gian hiện tại: {current_time.isoformat()}")
        
        if scheduled_time <= current_time:
            # Nếu thời gian đã qua, gửi ngay
            print(f"⚡ Thời gian đã qua, gửi ngay email ID={email_id}")
            send_email_task.delay(email_id)
        else:
            # Schedule với ETA chính xác
            time_diff = scheduled_time - current_time
            print(f"⏳ Sẽ gửi sau {time_diff.total_seconds():.1f} giây")
            
            task_result = send_email_task.apply_async(
                args=[email_id],
                eta=scheduled_time,
                task_id=f"email_{email_id}_{int(scheduled_time.timestamp())}"
            )
            
            print(f"✅ Email ID={email_id} đã được lên lịch với Task ID: {task_result.id}")
            
            # Cập nhật status trong database để theo dõi
            conn = sqlite3.connect('emails.db')
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE emails SET status='scheduled' WHERE id=?", 
                (email_id,)
            )
            conn.commit()
            conn.close()
            
            return task_result.id
            
    except Exception as e:
        error_time = datetime.now().isoformat()
        print(f"[{error_time}] ❌ LỖI schedule email ID={email_id}: {str(e)}")
        traceback.print_exc()
        return None
