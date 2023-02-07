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
from dataclasses import dataclass

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

"""
SQLALCHEMY MODELS
"""


@dataclass
class DataTypes(db.Model):
    __tablename__ = "data_types"

    id: int
    data_type: str
    created_on: str

    id = db.Column(db.Integer, primary_key=True)
    data_type = db.Column(db.String(), unique=True)
    created_on = db.Column(db.DateTime, server_default=db.func.now())

    def __init__(self, id=None, data_type=None, created_on=None):
        self.id = id
        self.data_type = data_type
        self.created_on = created_on

@dataclass
class TopicSubscription(db.Model):
    __tablename__ = "subscriptions"

    id: int
    address: str
    subscribe: bool
    graph: bool
    data_type: str
    created_on: str
    updated_on: str
    columns: str
    high_freq: bool
    deleted: bool

    id = db.Column(db.Integer, primary_key=True)
    address = db.Column(db.String(), unique=False)
    subscribe = db.Column(db.Boolean, nullable=False, default=False)
    graph = db.Column(db.Boolean, nullable=False, default=False)
    data_type = db.Column(db.Text, nullable=False)
    created_on = db.Column(db.DateTime, server_default=db.func.now())
    updated_on = db.Column(
        db.DateTime, server_default=db.func.now(), onupdate=db.func.now()
    )

    columns = db.Column(db.Text, nullable=True)
    high_freq = db.Column(db.Boolean, nullable=False, default=False)
    deleted = db.Column(db.Boolean, nullable=False, default=False)

    def __repr__(self):
        return f"#{self.id} address: {self.address} subscribing: {self.subscribe} graph: {self.graph} data type: {self.data_type} columns: {self.columns} high_freq: {self.high_freq} deleted: {self.deleted} created: {self.created_on} updated: {self.updated_on}"

    def to_dict(self):
        return dict(
            id=self.id,
            address=self.address,
            subscribe=self.subscribe,
            graph=self.graph,
            data_type=self.data_type,
            columns=self.columns,
            high_freq=self.high_freq,
            deleted=self.deleted,
            created_on=self.created_on.isoformat(),
            updated_on=self.updated_on.isoformat(),
        )


@dataclass
class Mqtt(db.Model):
    __tablename__ = "mqtt"

    id: int
    topic: str
    value: str
    timestamp: str
    created_on: str
    updated_on: str

    topic_id: int

    topic_id = db.Column(db.Integer, db.ForeignKey("subscriptions.id"), nullable=True)

    id = db.Column(db.Integer, primary_key=True)
    topic = db.Column(db.Text, nullable=False)
    value = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    created_on = db.Column(db.DateTime, server_default=db.func.now())
    updated_on = db.Column(
        db.DateTime, server_default=db.func.now(), onupdate=db.func.now()
    )

    def __repr__(self):
        return f"{self.id} {self.topic} {self.topic_id} {self.timestamp} created: {self.created_on} updated: {self.updated_on} value: {self.value}"

    def to_dict(self):
        return dict(
            id=self.id,
            topic=self.topic,
            value=self.value,
            timestamp=self.timestamp.isoformat(),
            topic_id=self.topic_id,
            created_on=self.created_on.isoformat(),
            updated_on=self.updated_on.isoformat(),
        )


@dataclass
class NotificationLog(db.Model):
    __tablename__ = "notification_alert_logs"

    id: int
    message: str
    timestamp: str
    created_on: str
    updated_on: str
    address: str

    notification_alert_id: int

    id = db.Column(db.Integer, primary_key=True)
    message = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    created_on = db.Column(db.DateTime, server_default=db.func.now())
    updated_on = db.Column(
        db.DateTime, server_default=db.func.now(), onupdate=db.func.now()
    )
    address = db.Column(db.Text)

    notification_alert_id = db.Column(
        db.Integer, db.ForeignKey("alert_rule.id"), nullable=True
    )

    alert_rule = db.relationship("AlertRule", back_populates="notification_logs")

    def __repr__(self):
        return f"{self.id} message: {self.message} address: {self.address} t: {self.timestamp} created: {self.created_on} updated: {self.updated_on}"


@dataclass
class AlertCompOperators(db.Model):
    __tablename__ = "alert_comp_operators"

    id: int
    op: str

    id = db.Column(db.Integer, primary_key=True)
    op = db.Column(db.String(), nullable=False, unique=True)

    def __init__(self, id=None, op=None):
        self.id = id
        self.op = op


@dataclass
class AlertFunctions(db.Model):
    __tablename__ = "alert_functions"

    id: int
    op: str

    id = db.Column(db.Integer, primary_key=True)
    op = db.Column(db.String(), nullable=False, unique=True)

    def __init__(self, id=None, op=None):
        self.id = id
        self.op = op


@dataclass
class AlertRule(db.Model):
    __tablename__ = "alert_rule"

    id: int
    rule: str
    rule_value: float
    active: bool
    address: str
    column: str

    notify_by_email: bool
    email: str
    email_cooldown: int
    raised: bool
    timestamp: str

    topic_id: int
    notification_logs = NotificationLog

    func: str
    func_time: bool
    func_time_n: int

    created_on: str
    updated_on: str

    id = db.Column(db.Integer, primary_key=True)
    rule = db.Column(db.String())
    rule_value = db.Column(db.Float, nullable=False, default=0.0)

    active = db.Column(db.Boolean(), default=True)
    address = db.Column(db.String())
    column = db.Column(db.String(), nullable=True, default=None)

    notify_by_email = db.Column(db.Boolean, nullable=False, default=False)
    email = db.Column(db.String(320), nullable=True, default=None)
    email_cooldown = db.Column(db.Integer(), default=300)
    raised = db.Column(db.Boolean(), default=False)
    timestamp = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    topic_id = db.Column(db.Integer, db.ForeignKey("subscriptions.id"), nullable=True)
    notification_logs = db.relationship("NotificationLog", back_populates="alert_rule")

    func = db.Column(db.String(), nullable=True, default=None)
    func_time = db.Column(db.Boolean(), default=False, nullable=True)
    func_time_n = db.Column(db.Integer(), default=2, nullable=True)

    created_on = db.Column(db.DateTime, server_default=db.func.now())
    updated_on = db.Column(
        db.DateTime, server_default=db.func.now(), onupdate=db.func.now()
    )

    def __repr__(self):
        return f"#{self.id} active: {self.active} column: {self.column} rule: {self.rule} value: {self.rule_value} subscribing: {self.address} notify by email: {self.notify_by_email}"

    def to_dict(self):
        return dict(
            id=self.id,
            rule=self.rule,
            rule_value=self.rule_value,
            active=self.active,
            address=self.address,
            column=self.column,
            notify_by_email=self.notify_by_email,
            email=self.email,
            email_cooldown=self.email_cooldown,
            raised=self.raised,
            timestamp=self.timestamp.isoformat(),
            topic_id=self.topic_id,
            func=self.func,
            func_time=self.func_time,
            func_time_n=self.func_time_n,
            created_on=self.created_on.isoformat(),
            updated_on=self.updated_on.isoformat(),
        )


def create_default_data(app):
    timestamp = datetime.datetime.now()

    def createDataType(id, data_type):
        try:
            instance = (
                db.session.query(DataTypes).filter_by(data_type=data_type).one_or_none()
            )

            if not instance:
                instance = DataTypes(id=id, data_type=data_type, created_on=timestamp)
                db.session.add(instance)
                db.session.commit()
        except Exception as ex:
            db.session.rollback()
            app.logger.exception(ex)

    list(map(createDataType, [0, 1, 2, 3], ["single", "csv", "json", "json_lab"]))

    def createAlertCompOperator(id, op):
        try:
            instance = (
                db.session.query(AlertCompOperators).filter_by(op=op).one_or_none()
            )
            if not instance:
                r = AlertCompOperators(id, op)
                db.session.add(r)
                db.session.commit()
        except Exception as ex:
            db.session.rollback()
            app.logger.exception(ex)

    list(
        map(
            createAlertCompOperator,
            [0, 1, 2, 3, 4, 5],
            ["<", "<=", ">", ">=", "==", "!="],
        )
    )

    def createAlertFunction(id, op):
        try:
            instance = db.session.query(AlertFunctions).filter_by(op=op).one_or_none()
            if not instance:
                r = AlertFunctions(id, op)
                db.session.add(r)
                db.session.commit()
        except Exception as ex:
            db.session.rollback()
            app.logger.exception(ex)

    list(
        map(
            createAlertFunction,
            [0, 1, 2, 3, 4, 5, 6, 7],
            [
                "Mean",
                "Mode",
                "Median",
                "Max",
                "Min",
                "Standard deviation",
                "Change",
                "Percent change",
            ],
        )
    )
