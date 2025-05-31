# Email Management System

Hệ thống quản lý và gửi Email sử dụng Flask, Celery và Redis với tính năng phân loại ưu tiên và hẹn giờ gửi tự động.

## 🚀 Hướng dẫn cài đặt nhanh

### Bước 1: Clone dự án
```bash
git clone <repository-url>
cd email_system
```

### Bước 2: Cập nhật thông tin email
Mở file `email_system/.env` và cập nhật thông tin Gmail của bạn:
```env
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your_email@gmail.com
SMTP_PASSWORD=your_app_password
SENDER_EMAIL=your_email@gmail.com
```

**⚠️ Quan trọng:** Sử dụng App Password của Gmail, không phải mật khẩu thường!

### Bước 3: Chạy hệ thống
```bash
cd email_system
run.bat
```

Sau khi chạy thành công, mở trình duyệt tại: **http://localhost:5000**

## 📋 Yêu cầu hệ thống

- **Python 3.8+**
- **Redis Server** (hoặc Docker)
- **Gmail account** với App Password

## 🔧 Cài đặt thủ công (nếu run.bat không hoạt động)

### 1. Cài đặt Redis

**Tùy chọn A: Sử dụng Docker (khuyến nghị)**
```powershell
docker run -d --name redis-email -p 6379:6379 redis:alpine
```

**Tùy chọn B: Cài đặt Redis cho Windows**
- Tải từ: https://github.com/microsoftarchive/redis/releases
- Hoặc cài qua Chocolatey:
```powershell
choco install redis-64
```

**Tùy chọn C: Sử dụng WSL**
```bash
sudo apt install redis-server
redis-server
```

### 2. Cài đặt Python dependencies
```powershell
cd email_system
python -m venv venv
venv\Scripts\Activate.ps1
pip install flask celery redis python-dotenv
```

### 3. Chạy các dịch vụ

**Terminal 1: Redis Server**
```powershell
redis-server
```

**Terminal 2: Celery Worker**
```powershell
cd email_system
venv\Scripts\Activate.ps1
celery -A tasks worker --loglevel=info --pool=solo
```

**Terminal 3: Celery Beat**
```powershell
cd email_system
venv\Scripts\Activate.ps1
celery -A tasks beat --loglevel=info
```

**Terminal 4: Flask App**
```powershell
cd email_system
venv\Scripts\Activate.ps1
python app.py
```

## 📧 Cách lấy Gmail App Password

1. Đăng nhập Gmail → **Google Account Settings**
2. **Security** → **2-Step Verification** (bật nếu chưa có)
3. **App passwords** → **Generate new password**
4. Chọn **Mail** và **Other (Custom name)**
5. Copy mật khẩu 16 ký tự vào file `.env`

## 🎯 Tính năng chính

### ✨ Gửi Email với Priority
- **High Priority**: Gửi ngay lập tức
- **Medium Priority**: Gửi trong vòng 5 phút
- **Low Priority**: Gửi trong vòng 15 phút

### ⏰ Hẹn giờ gửi Email
- Lên lịch gửi email tự động
- Hỗ trợ múi giờ Việt Nam
- Theo dõi trạng thái real-time

### 📊 Dashboard quản lý
- Xem danh sách email đã gửi
- Theo dõi trạng thái: Pending, Sent, Failed
- Lọc theo priority và thời gian

## 🗂️ Cấu trúc dự án

```
email_system/
├── email_system/
│   ├── app.py              # Flask web application
│   ├── tasks.py            # Celery tasks xử lý email
│   ├── run.bat             # Script khởi động tự động
│   ├── .env                # Cấu hình email (cần cập nhật)
│   ├── emails.db           # SQLite database
│   ├── templates/          # HTML templates
│   │   ├── inbox.html
│   │   ├── send_email.html
│   │   └── view_email.html
│   └── static/
│       └── requirements.txt
└── README.md
```

## 🛠️ Troubleshooting

### Lỗi kết nối Redis
```
ConnectionError: Error 10061 connecting to localhost:6379
```
**Giải pháp:** Khởi động Redis server trước khi chạy ứng dụng

### Lỗi xác thực Gmail
```
SMTPAuthenticationError: Username and Password not accepted
```
**Giải pháp:** 
- Kiểm tra Gmail App Password
- Bật 2-Step Verification
- Sử dụng App Password thay vì mật khẩu thường

### Lỗi Celery Worker
```
kombu.exceptions.OperationalError: [Errno 10061]
```
**Giải pháp:** Đảm bảo Redis đang chạy và accessible

### Lỗi thiếu module
```
ModuleNotFoundError: No module named 'flask'
```
**Giải pháp:** 
```powershell
pip install flask celery redis python-dotenv
```

## 🔍 Testing

### Test kết nối Redis
```powershell
redis-cli ping
# Kết quả: PONG
```

### Test gửi email đơn giản
1. Mở http://localhost:5000
2. Click **"Compose Email"**
3. Điền thông tin và chọn **High Priority**
4. Kiểm tra email đến trong inbox

### Test Celery Worker
```powershell
celery -A tasks inspect active
```

## 📝 Logs và Debug

### Xem log Celery
- Worker logs: Console window "Celery Worker"
- Beat logs: Console window "Celery Beat"

### Xem Flask logs
- Application logs: Console window "Flask App"
- Debug mode: Enabled by default



**Phát triển bởi:** [Trần Tuấn Anh & Nguyễn Hoàng BáchBách]
**Ngày cập nhật:** May 2025
