"""Daily scheduler for auto-generating copies before work."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from config import DEFAULT_SCHEDULE_HOUR, DEFAULT_SCHEDULE_MINUTE
from utils.db import get_setting, set_setting, save_copy
from generator.copywriter import generate_free


_scheduler = None


def _auto_generate():
    """Called by scheduler each day to generate copies automatically."""
    topic = get_setting("auto_topic", "通用")
    count = int(get_setting("auto_count", "3"))
    length = get_setting("auto_length", "60秒")
    style = get_setting("auto_style", "口语化")
    purpose = get_setting("auto_purpose", "涨粉")
    content_format = get_setting("auto_content_format", "单人口播")

    today_str = datetime.now().strftime("%Y-%m-%d")
    generated = []

    for i in range(count):
        try:
            result = generate_free(
                topic=f"{topic} {today_str}",
                length=length,
                style=style,
                purpose=purpose,
                content_format=content_format
            )
            title = f"【自动】{today_str} 第{i+1}条 - {topic}"
            save_copy(title, result, mode="free", length=length, style=style, purpose=purpose)
            generated.append(title)
        except Exception as e:
            print(f"Auto-generate error (iter {i}): {e}")

    set_setting("last_auto_gen", datetime.now().isoformat())
    set_setting("last_auto_gen_result", f"生成 {len(generated)} 条")
    return generated


def get_schedule_time() -> tuple[int, int]:
    hour = int(get_setting("schedule_hour", str(DEFAULT_SCHEDULE_HOUR)))
    minute = int(get_setting("schedule_minute", str(DEFAULT_SCHEDULE_MINUTE)))
    return hour, minute


def set_schedule_time(hour: int, minute: int):
    set_setting("schedule_hour", str(hour))
    set_setting("schedule_minute", str(minute))
    if _scheduler and _scheduler.running:
        _reschedule_job()


def _reschedule_job():
    if _scheduler:
        hour, minute = get_schedule_time()
        trigger = CronTrigger(hour=hour, minute=minute)
        _scheduler.reschedule_job("daily_gen", trigger=trigger)


def start_scheduler():
    """Start the background scheduler. Call once on app startup."""
    global _scheduler
    if _scheduler and _scheduler.running:
        return False

    _scheduler = BackgroundScheduler()
    hour, minute = get_schedule_time()
    _scheduler.add_job(
        _auto_generate,
        trigger=CronTrigger(hour=hour, minute=minute),
        id="daily_gen",
        name="Daily Copy Generation",
        replace_existing=True
    )
    _scheduler.start()
    return True


def stop_scheduler():
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        _scheduler = None


def is_scheduler_running() -> bool:
    return _scheduler is not None and _scheduler.running


def get_next_run_time():
    if _scheduler and _scheduler.running:
        job = _scheduler.get_job("daily_gen")
        if job:
            return job.next_run_time
    return None


def manual_generate_now():
    """Trigger generation immediately (for manual use)."""
    return _auto_generate()
