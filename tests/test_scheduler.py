from apscheduler.schedulers.background import BackgroundScheduler

from app.services.scheduler import DigestScheduler


def test_scheduler_registers_and_replaces_single_daily_job():
    backend = BackgroundScheduler()
    scheduler = DigestScheduler(lambda: None, backend=backend)

    scheduler.configure({"push_time": "08:30", "timezone": "Asia/Shanghai"})
    first = backend.get_job("daily-digest")
    scheduler.configure({"push_time": "10:15", "timezone": "Asia/Shanghai"})
    updated = backend.get_job("daily-digest")

    assert first is not None
    assert str(first.trigger) == "cron[hour='8', minute='30']"
    assert str(updated.trigger) == "cron[hour='10', minute='15']"
    assert updated.trigger.timezone.key == "Asia/Shanghai"
    assert len(backend.get_jobs()) == 1

