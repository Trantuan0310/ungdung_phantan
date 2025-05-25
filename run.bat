@echo off
cd /d %~dp0

REM Kích hoạt môi trường ảo (venv nằm bên ngoài thư mục email_system)
IF EXIST ..\venv\Scripts\activate (
    call ..\venv\Scripts\activate
)

REM Cài đặt các thư viện cần thiết (chỉ cài nếu chưa có)
pip install --upgrade pip
pip install celery python-dotenv

REM Khởi động Redis server (nếu đã cài redis-server vào PATH)
start cmd /k "redis-server"

REM Đợi Redis khởi động
timeout /t 3

REM Khởi động Celery worker
cd ..
cd email_system
start cmd /k "celery -A tasks worker --loglevel=info --pool=solo"

REM Đợi Celery khởi động
timeout /t 2

REM Khởi động ứng dụng chính (thay app.py bằng file main của bạn nếu khác)
start cmd /k "python app.py"

cd ..