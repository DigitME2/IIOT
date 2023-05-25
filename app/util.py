"""
Copyright 2023 DigitME2

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""
import datetime
import json
from dataclasses import dataclass

from apscheduler.schedulers.background import BackgroundScheduler


def is_float(s):
    try:
        float(s)
    except ValueError as e:
        return False
    return True


def is_json(data):
    try:
        json.loads(data)
    except ValueError as e:
        return False
    return True


# if timestamp doesn't have timezone, set to UTC (by default)
def set_tz_utc_if_none(timestamp, tz=datetime.timezone.utc):
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=tz)
    return timestamp


# This class is used to store the mqtt data and save it to the database by using bulk transaction
class BackgroundSchedulerFlask(BackgroundScheduler):

    def __init__(self, app=None):
        super().__init__()

        self.app = app
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        self.app = app


# This is used to periodically save the bulk MQTT data to the database.
@dataclass
class TimerBulkSave:
    first_mqtt_timestamp: datetime.datetime
    last_mqtt_timestamp: datetime.datetime
    every_seconds: float

    mqtt_objects: list

    sched: BackgroundSchedulerFlask


# This is used to count the number of transactions
@dataclass
class TimerCounter:
    first_mqtt_timestamp: datetime.datetime
    last_mqtt_timestamp: datetime.datetime
    every_seconds: float
    counter: int


def time_ago(dt):
    now = datetime.datetime.now(datetime.timezone.utc)
    dt = set_tz_utc_if_none(dt)
    diff = now - dt
    if diff.days > 0:
        return f"{diff.days} days ago"
    elif diff.seconds > 3600:
        return f"{diff.seconds // 3600} hours ago"
    elif diff.seconds > 60:
        return f"{diff.seconds // 60} minutes ago"
    else:
        return f"{diff.seconds} seconds ago"