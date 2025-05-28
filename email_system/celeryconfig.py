from celery.schedules import crontab

beat_schedule = {
    'check-scheduled-emails': {
        'task': 'tasks.check_scheduled_emails',
        'schedule': 60.0,  # Kiểm tra mỗi 60 giây
    },
}