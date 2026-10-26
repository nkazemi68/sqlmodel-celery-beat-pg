from fastapi import FastAPI
from sqladmin import Admin, ModelView
from .models import (
    ClockedSchedule, CrontabSchedule, IntervalSchedule,
    PeriodicTask, PeriodicTaskChanged, SolarSchedule,
)
from .session import SessionManager

class IntervalScheduleAdmin(ModelView, model=IntervalSchedule):
    name = "Interval Schedule"; column_list = ["id", "every", "period"]

class CrontabScheduleAdmin(ModelView, model=CrontabSchedule):
    name = "Crontab Schedule"

class SolarScheduleAdmin(ModelView, model=SolarSchedule):
    name = "Solar Schedule"

class ClockedScheduleAdmin(ModelView, model=ClockedSchedule):
    name = "Clocked Schedule"

class PeriodicTaskAdmin(ModelView, model=PeriodicTask):
    name = "Periodic Task"
    column_list = ["id", "name", "task", "discriminator", "schedule_id", "enabled", "one_off"]
    column_searchable_list = ["name", "task"]

class PeriodicTaskChangedAdmin(ModelView, model=PeriodicTaskChanged):
    name = "Change Marker"; can_create = can_edit = can_delete = False

def build_app(session_mgr: SessionManager, title: str = "Celery Beat Admin") -> FastAPI:
    app = FastAPI(title=title)
    admin = Admin(app, session_mgr.engine, title=title, base_url="/admin")
    for v in (IntervalScheduleAdmin, CrontabScheduleAdmin, SolarScheduleAdmin,
              ClockedScheduleAdmin, PeriodicTaskAdmin, PeriodicTaskChangedAdmin):
        admin.add_view(v)
    return app