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

import ast
import logging
import os
import sqlite3
import traceback
import urllib
from io import StringIO
from logging.handlers import RotatingFileHandler
from threading import Thread
from typing import Union

import dash
import numpy as np
import paho.mqtt.client as mqtt
import pandas as pd
import plotly.express as px
import plotly.graph_objs as go
from dash import callback_context, dcc, html
from dash.dependencies import Input, Output
from flask import Flask, current_app, g, jsonify, url_for
from flask_compress import Compress
from flask_mail import Mail, Message
from flask_migrate import Migrate
from flask_socketio import SocketIO, emit
from sqlalchemy import and_, text
from sqlalchemy.exc import SQLAlchemyError

from app.middlewares import RequestTimeMiddleware
from app.models import (AlertRule, Mqtt, NotificationLog, TopicSubscription,
                        create_default_data, db)
from app.util import *
from config import Config

is_updating = False

mqttc = mqtt.Client()
migrate = Migrate()
myemail = Mail()
socketio = SocketIO(async_mode='threading',
                    engineio_logger=False,
                    logger=False)
flask_compress = Compress()

# Scheduler that is used to periodically save the bulk MQTT data to the database.
timerBulkSave = TimerBulkSave(
    datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1),
    datetime.datetime.now(datetime.timezone.utc), 10.0, [],
    BackgroundSchedulerFlask())
timerBulkSave.first_mqtt_timestamp = timerBulkSave.first_mqtt_timestamp.replace(
    tzinfo=datetime.timezone.utc)

# This is used to count the number of transactions.
timerCounter = TimerCounter(
    datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1),
    datetime.datetime.now(datetime.timezone.utc), 1.0, 0)
timerCounter.first_mqtt_timestamp = timerCounter.first_mqtt_timestamp.replace(
    tzinfo=datetime.timezone.utc)


# Saves the data stored in timerBulkSave.mqtt_objects to database and clears the contents of timerBulkSave.mqtt_objects
def bulk_save_scheduler() -> bool:
    if len(timerBulkSave.mqtt_objects) <= 0:
        return False
    with timerBulkSave.sched.app.app_context():
        db.session.bulk_save_objects(timerBulkSave.mqtt_objects)
        db.session.commit()
        timerBulkSave.mqtt_objects.clear()
        return True


# This uses SQLAlchemy ORM to save the object to the database
def store_mqtt_record(topic: TopicSubscription, value: str,
                      timestamp: Union[str, datetime.datetime]) -> bool:
    try:
        mqtt_record = Mqtt(topic=topic.address,
                           value=value,
                           timestamp=timestamp,
                           topic_id=topic.id)
        # If data is coming in high frequency (Usually more than >5 samples per second) we should mark it as high_freq and save it in bulk.
        if topic.high_freq:
            start_database_save_scheduler(timerBulkSave)
            timerBulkSave.mqtt_objects.append(mqtt_record)
        else:
            db.session.add(mqtt_record)
            db.session.commit()
        return True
    # If there is an error, log it
    except SQLAlchemyError as e:
        current_app.logger.error(str(e.orig))
        return False


# This function starts the scheduler that will periodically save the data to the database in bulk
def start_database_save_scheduler(timer_bulk_save_obj: TimerBulkSave) -> bool:
    if not timer_bulk_save_obj.sched.running:
        timer_bulk_save_obj.sched.add_job(
            bulk_save_scheduler,
            'interval',
            seconds=timer_bulk_save_obj.every_seconds)
        timer_bulk_save_obj.sched.start()
        return True
    return False


# Raw SQLite implementation
def store_mqtt_record_sqlite(con, topic: str, value: str,
                             timestamp: str) -> bool:
    try:
        con.cursor().execute(
            f'INSERT INTO mqtt (topic, value, timestamp) values (\'{topic}\', \'{value}\', \'{timestamp}\');'
        )
        con.commit()
        con.close()
        return True
    except sqlite3.Error as er:
        current_app.logger.error(str(er))
        return False


# Wraps function in a Thread and starts it
def async_thread(f):

    def wrapper(*args, **kwargs):
        thr = Thread(target=f, args=args, kwargs=kwargs)
        thr.start()

    return wrapper


# Returns empty layout with custom text.
def empty_layout(message="No data to display"):
    return {
        "layout": {
            "paper_bgcolor":
            'rgba(0,0,0,0)',
            "plot_bgcolor":
            'rgba(0,0,0,0)',
            "xaxis": {
                "visible": False
            },
            "yaxis": {
                "visible": False
            },
            "annotations": [{
                "text": message,
                "xref": "paper",
                "yref": "paper",
                "showarrow": False,
                "font": {
                    "size": 34,
                    "color": 'rgb(246, 149, 58)'
                }
            }]
        }
    }


# Generate indexes for the SQL database to speed up queries.
def gen_default_indexes(app: Flask, db_instance):
    if app.config.get('TESTING'):
        return
    generate_index(
        app,
        'CREATE INDEX mqtt_topic_timestamp_IDX ON mqtt (topic,"timestamp");',
        db_instance)
    generate_index(
        app,
        'CREATE INDEX mqtt_topic_id_timestamp_IDX ON mqtt (topic_id,"timestamp");',
        db_instance)
    generate_index(
        app,
        'CREATE INDEX mqtt_timestamp_IDX ON mqtt ("timestamp");',
        db_instance)


# Execute index query operation on SQL database
def generate_index(app: Flask, arg1: str, db_instance):
    try:
        app.logger.info(arg1)
        with db_instance.engine.connect() as connection:
            connection.execute(text(arg1))
    except SQLAlchemyError as er:
        app.logger.exception(er)


# Gets the number of active sensors (topic subscriptions) where subscription is active
def get_number_of_active_sensors(db_instance) -> int:
    with db_instance.engine.connect() as connection:
        result = connection.execute(
            text(
                "SELECT COUNT(subscribe) from subscriptions where subscribe = 1;"
            ))
        for r in result:
            return r._data[0]
    return 0


# Gets the number of inactive sensors (topic subscriptions) where subscription is not active
def get_number_of_inactive_sensors(db_instance) -> int:
    with db_instance.engine.connect() as connection:
        result = connection.execute(
            text(
                "SELECT COUNT(subscribe) from subscriptions where subscribe = 0;"
            ))
        for r in result:
            return r._data[0]
    return 0


# Get the TopicSubscriptions with graph option set to True
def get_topics_graph(app: Flask):
    with app.app_context():
        return TopicSubscription.query.filter_by(graph=1).all()


# Updates the g variable
def update_g_varaible(db):
    g.number_of_active_sensors = get_number_of_active_sensors(db)
    g.number_of_inactive_sensors = get_number_of_inactive_sensors(db)


# Generate figure based on df data and topic subscription
def create_figure(df_topic: pd.DataFrame,
                  topic_subscription: TopicSubscription):
    if df_topic.empty:
        return empty_layout()

    try:
        if topic_subscription.data_type == 'single':
            return convert_single_data_type_data_to_fig(df_topic)
        elif topic_subscription.data_type == 'csv':
            return return_empty_figure()  # TODO: OBSOLETE
        elif topic_subscription.data_type == 'json':
            if topic_subscription.columns is None:
                columns = ['value']
            else:
                columns = json.loads(topic_subscription.columns)
            return convert_json_data_to_fig(df_topic, columns)
        elif topic_subscription.data_type == 'json_lab':
            return convert_json_lab_data_to_fig(
                df_topic, json.loads(topic_subscription.columns))
        else:
            current_app.logger.error(
                f'Unknown data type {topic_subscription.data_type}')
            return return_empty_figure()
    except Exception as ex:
        current_app.logger.error(ex)
        return return_empty_figure()


# This function is used to get the list of files that ends with extension in static flask folder
def get_file_list(static_folder: str, endswith='.') -> list:
    file_list = []
    for f in [
            f for f in os.listdir(
                os.path.join(current_app.static_folder, static_folder))
            if f.endswith(endswith)
    ]:
        img_url = url_for('static',
                          filename=os.path.join(static_folder,
                                                f).replace("\\", "/"))
        img_url = urllib.parse.unquote(img_url)
        file_list.append(img_url)

    return file_list


def return_empty_figure() -> go.Figure:
    df_topic = pd.DataFrame({})
    return px.line(df_topic)


# Initialize logger
def init_logger(app: Flask,
                formatter: str,
                log_dir: str,
                max_bytes=10000000,
                backup_count=10):
    # Create directory if it doesn't exist
    if not os.path.exists(log_dir):
        os.mkdir(log_dir)

    # Set formatting
    rfh_formatter = logging.Formatter(formatter)
    # Create Rotating File Handler
    rfh = RotatingFileHandler(filename=f'{log_dir}/app.log',
                              maxBytes=max_bytes,
                              backupCount=backup_count)
    rfh.setFormatter(rfh_formatter)

    # Set logging mode
    if app.config.get('DEBUG'):
        rfh.setLevel(logging.DEBUG)
    else:
        rfh.setLevel(logging.INFO)

    # Add Logging Handler to Flask
    app.logger.addHandler(rfh)


# Initialize the Flask application instance
def init_app(config=None) -> Flask:
    app = Flask(__name__)
    if config is None:
        app.config.from_object(Config)
    else:
        app.config.from_object(config)

    # If we want to measure how much time it takes to process a request we can set
    # the option PRINT_REQUEST_PROCESS_TIME to true
    if app.config.get('PRINT_REQUEST_PROCESS_TIME'):
        app.wsgi_app = RequestTimeMiddleware(app.wsgi_app)

    myemail.init_app(app)
    socketio.init_app(app)
    flask_compress.init_app(app)
    timerBulkSave.sched.init_app(app)

    app_dash = dash.Dash(__name__, server=app, url_base_pathname='/dashapp/')
    init_logger(
        app, '%(asctime)s %(levelname)s %(name)s %(threadName)s : %(message)s',
        'logs')

    app.logger.debug('Debug message')
    app.logger.info('Info message')
    app.logger.warning('Warning message')
    app.logger.error('Error message')
    app.logger.info(app.config)
    with app.app_context():
        app.logger.info('Starting server...')
        db.init_app(app)
        db.create_all()
        db.session.commit()
        app.logger.info('DB initialized.')

        # Enable WAL for SQLITE database
        with db.engine.connect() as connection:
            connection.execute(text("PRAGMA journal_mode = WAL"))
            connection.execute(text("PRAGMA synchronous = NORMAL"))
            connection.close()

        # migrate.init_app(app, db)
        generate_default_data(app, db)

        global is_updating
        is_updating = False
        g.number_of_active_sensors = None
        g.number_of_inactive_sensors = None
        if g.number_of_active_sensors is None:
            g.number_of_active_sensors = get_number_of_active_sensors(db)
        if g.number_of_inactive_sensors is None:
            g.number_of_inactive_sensors = get_number_of_inactive_sensors(db)

    # Create Dash Layout
    def dash_layout(update_interval: int):
        return html.Div(children=[
            html.Div(children=[
                html.B(
                    'Refreshed At: ' +
                    str(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                    id='last_update'),
                dcc.Store(id='SELECTED_TOPIC', storage_type='session'),
            ]),
            dcc.Location(id='url_location', refresh=False),
            html.Div(children=[
                dcc.Graph(id='fig_topic', figure=empty_layout("Loading...")),
            ]),
            dcc.Interval(
                id='update_interval', interval=update_interval, n_intervals=0),
            html.Div(id='div_data_table'),
            html.Div(id='div_dummy')
        ])

    dash_update_interval = app.config.get('DASH_UPDATE_INTERVAL') or 30000
    app_dash.layout = dash_layout(dash_update_interval)

    # Define Dash Callbacks
    @app_dash.callback(Output('last_update', 'children'),
                       Output('fig_topic', 'figure'),
                       Input('update_interval', 'n_intervals'),
                       Input('url_location', 'search'))
    def update_fig_topic(interval_val, pathname):
        parsed = urllib.parse.urlparse(pathname)
        parsed_dict = urllib.parse.parse_qs(parsed.query)

        if len(parsed_dict) == 0:
            return 'Refreshed At: ' + str(datetime.datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S")), empty_layout()

        topic_address = parsed_dict.get('address')[0]
        if topic_address == "" or topic_address is None:
            return 'Refreshed At: ' + str(datetime.datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S")), empty_layout()

        topic_id = parsed_dict.get('id')[0]
        if topic_id == "" or topic_id is None:
            return 'Refreshed At: ' + str(datetime.datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S")), empty_layout()

        global is_updating

        if callback_context.triggered[0][
                'prop_id'] == 'update_interval.n_intervals':
            pass
        elif callback_context.triggered[0][
                'prop_id'] == 'topic_dropdown.value':
            is_updating = False

        if is_updating:
            return dash.no_update
        if not is_updating:
            is_updating = True

            df_topic_query = db.session.query(Mqtt).filter_by(
                topic_id=topic_id).order_by(Mqtt.timestamp.desc()).limit(500)
            df_topic = pd.read_sql_query(df_topic_query.statement,
                                         db.session.connection())

            if df_topic.empty:
                fig_topic = empty_layout()
                is_updating = False
                return 'Refreshed At: ' + str(datetime.datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S")), fig_topic

            topic_subscription = TopicSubscription.query.filter_by(
                id=topic_id).first()

            fig_topic = create_figure(df_topic, topic_subscription)
            fig_topic['layout']['uirevision'] = 'uirevision'
            is_updating = False
            return 'Refreshed At: ' + str(datetime.datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S")), fig_topic

    if not app.config.get('TESTING'):
        global mqttc
        mqttc = init_mqtt(app)
    from .routes import main_blueprint
    app.register_blueprint(main_blueprint)
    app.logger.info('Server started!')
    return app

def update_db(app, db):
    # Add deleted bool column to Topic subscription table
    try:
        with db.engine.connect() as connection:
            connection.execute(text("ALTER TABLE subscriptions ADD COLUMN deleted BOOLEAN DEFAULT 0 NOT NULL;"))
    except SQLAlchemyError as er:
        app.logger.exception(er)

def generate_default_data(app: Flask, db):
    gen_default_indexes(app, db)
    create_default_data(app)
    update_db(app, db)


# Subscribe to the list of tuples MQTT topics (mqtt_topic, qos_level)
def subscribe_to_mqtt_topics(app: Flask, mqtt_client: mqtt.Client,
                             mqtt_topics: list[tuple[str, int]]) -> bool:
    if mqtt_topics:
        mqtt_client.subscribe(mqtt_topics)
        return True
    app.logger.info('No topics to subscribe')
    return False


# Get the MQTT Topic Subscriptions, and create tuple by adding QOS_LEVEL to them
# mqtt_topic -> (mqtt_topic, 2)
def get_mqtt_subs_tuple(app: Flask, qos_level: int) -> list[tuple]:
    with app.app_context():
        mqtt_topics = TopicSubscription.query.filter_by(
            subscribe=1).with_entities(TopicSubscription.address).all()
        mqtt_topics = [(*tup, qos_level) for tup in mqtt_topics]
    return mqtt_topics


# Initialize MQTT,
def init_mqtt(app: Flask) -> mqtt.Client:

    def on_connect(client, userdata, flags, rc):
        # If we successfully connected to the MQTT server, subscribe to all topics
        if rc == 0:
            app.logger.info(mqtt.error_string(rc) + ' Successfully connected')
            subscribe_to_mqtt_topics(app, mqttc, get_mqtt_subs_tuple(app, 2))
        else:
            app.logger.info('MQTT could not connect!' + mqtt.error_string(rc))

    # Log topics we have subscribed to
    def on_subscribe(client, userdata, mid, granted_qos):
        app.logger.info(
            f"Subscribe {str(userdata)} mid: {str(mid)} qos: {str(granted_qos)}"
        )

    # Log topics we have unsubscribed to
    def on_unsubscribe(client, userdata, mid):
        app.logger.info(f"Unsubscribe {str(userdata)} mid: {str(mid)}")

    def on_message(client, userdata, msg):
        try:
            value = str(msg.payload.decode("utf-8"))

            with app.app_context():
                topic_subscription = db.session.query(
                    TopicSubscription).filter(
                        TopicSubscription.address == msg.topic).filter(
                            TopicSubscription.deleted == False).first()

                timestamp = datetime.datetime.now(datetime.timezone.utc)
                if topic_subscription.data_type == 'single':
                    if store_single_mqtt_record(topic_subscription, value, timestamp):
                        check_alerts_for_single_value(topic_subscription, value, timestamp)

                elif topic_subscription.data_type == 'json':
                    json_obj = ast.literal_eval(value)
                    if store_json_mqtt_record(topic_subscription, json_obj):
                        broadcast_json_data(value, topic_subscription.id, topic_subscription.address, str(timestamp))
                        check_alerts_for_json_value(topic_subscription, json_obj, timestamp)
                elif topic_subscription.data_type == 'csv':
                    store_mqtt_record(topic_subscription,
                                      value.splitlines()[0], timestamp)
                elif topic_subscription.data_type == 'json_lab':
                    # Get timestamp from json_lab object (messageID), if failed get the timestamp from server
                    json_obj_datetime = get_datetime_from_json_lab(value, timestamp)
                    if store_mqtt_record(topic_subscription, value, json_obj_datetime):
                        broadcast_json_lab_data(value, topic_subscription.address,
                                            str(json_obj_datetime),
                                            topic_subscription.id)
                        check_alerts_for_json_lab(topic_subscription, value, json_obj_datetime)
                else:
                    app.logger.warning('unknown data type')
        except Exception as e:
            app.logger.exception("Exception on_message!")
            app.logger.exception(e)


    # Flask spawns two instances while running on Debug Mode. MQTT needs to have ONLY ONE instance to work properly.
    if os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        app.logger.info('Starting MQTT...')
        mqttc.on_connect = on_connect
        mqttc.on_message = on_message
        mqttc.on_subscribe = on_subscribe
        mqttc.on_unsubscribe = on_unsubscribe
        if not app.config.get('TESTING'):
            mqttc.connect(app.config.get('MQTT_URL'), 1883, 60)
            mqttc.loop_start()
            app.logger.info('MQTT started!')
        else:
            app.logger.info('MQTT testing started!')
    #####################
    return mqttc

def check_alerts_for_json_lab(topic_subscription, value, json_obj_datetime):
    obj = ast.literal_eval(value)

    if alerts := get_active_alerts_by_topic_id(topic_subscription.id):
        if topic_subscription.columns is None:
            check_alerts(alerts, topic_subscription, float(obj),
                                        json_obj_datetime)
        else:
            check_alerts_with_columns(alerts, topic_subscription,
                                              obj,
                                              json_obj_datetime,
                                              is_dict=True)

def check_alerts_for_json_value(topic_subscription, json_obj, timestamp):
    if alerts := get_active_alerts_by_topic_id(topic_subscription.id):
        if topic_subscription.columns is None:
            check_alerts(alerts, topic_subscription, float(json_obj['value']), timestamp)
        else:
            check_alerts_with_columns(alerts, topic_subscription, json_obj['value'], timestamp)	

def check_alerts_for_single_value(topic_subscription, value, timestamp):
    if alerts := get_active_alerts_by_topic_id(topic_subscription.id):
        check_alerts(alerts, topic_subscription, value, timestamp)


def get_datetime_from_json_lab(value, timestamp):
    try:
        json_obj = ast.literal_eval(value)
        json_obj_datetime_unix = float(
                        json_obj['messageID']) / 1000.0
        json_obj_datetime = datetime.datetime.fromtimestamp(
                        json_obj_datetime_unix)
        json_obj_datetime = json_obj_datetime.replace(
                        tzinfo=datetime.timezone.utc)

    except Exception as ex:
        json_obj_datetime = timestamp
    return json_obj_datetime

# Checks rule operation between value A and value B
def check_rule_operator(operator: str, val_a: Union[float, str, int],
                        val_b: Union[float, str, int]):
    try:
        if type(val_a) != float:
            val_a = float(val_a)
        if type(val_b) != float:
            val_b = float(val_b)
        if operator == "!=":
            return val_a != val_b
        elif operator == "<":
            return val_a < val_b
        elif operator == "<=":
            return val_a <= val_b
        elif operator == "==":
            return val_a == val_b
        elif operator == ">":
            return val_a > val_b
        elif operator == ">=":
            return val_a >= val_b
    except Exception as e:
        current_app.logger.exception(e)


# Executes function on dataframe
def check_function(function: str, df: pd.DataFrame):
    if df.empty:
        return None
    if function == 'Mean':
        return df.mean().values[0]
    elif function == 'Mode':
        return df.mode().values[0][0]
    elif function == 'Median':
        return df.median().values[0]
    elif function == 'Max':
        return df.max().values[0]
    elif function == 'Min':
        return df.min().values[0]
    elif function == 'Standard deviation':
        return df.std().values[0]
    elif function == 'Percent change':
        return df.pct_change()
    elif function == 'Change':
        return df.diff()
    else:
        return None


# Returns MQTT data from datetime to datetime with topic_id
def get_mqtt_data_from_to_datetime_by_id(
        topic_id: int, date_from: datetime.datetime,
        date_to: datetime.datetime) -> pd.DataFrame:
    cond = and_(Mqtt.timestamp.between(date_from, date_to),
                Mqtt.topic_id == topic_id)
    csv_topic_like = Mqtt.query.with_entities(
        Mqtt.id, Mqtt.topic, Mqtt.value, Mqtt.timestamp).filter(cond).all()
    return pd.DataFrame.from_records(
        csv_topic_like,
        index='id',
        columns=['id', 'topic', 'value', 'timestamp'])


# Returns MQTT data from date from to date to that has topic_id
def get_mqtt_data_from_to_by_id(topic_id: int, date_from: str,
                                date_to: str) -> pd.DataFrame:
    date_to_inclusive = datetime.datetime.strptime(
        date_to, '%Y-%m-%d') + datetime.timedelta(days=1)
    cond = and_(Mqtt.timestamp.between(date_from, date_to_inclusive),
                Mqtt.topic_id == topic_id)
    csv_topic_like = Mqtt.query.with_entities(
        Mqtt.id, Mqtt.topic, Mqtt.value, Mqtt.timestamp).filter(cond).all()
    return pd.DataFrame.from_records(
        csv_topic_like,
        index='id',
        columns=['id', 'topic', 'value', 'timestamp'])


# Returns MQTT data from date from to date to that has address address
def get_mqtt_data_from_to_by_address(address: str, date_from: str,
                                     date_to: str) -> pd.DataFrame:
    date_to_inclusive = datetime.datetime.strptime(
        date_to, '%Y-%m-%d') + datetime.timedelta(days=1)
    cond = and_(Mqtt.timestamp.between(date_from, date_to_inclusive),
                Mqtt.topic == address)
    csv_topic_like = Mqtt.query.with_entities(
        Mqtt.id, Mqtt.topic, Mqtt.value, Mqtt.timestamp).filter(cond).all()
    return pd.DataFrame.from_records(
        csv_topic_like,
        index='id',
        columns=['id', 'topic', 'value', 'timestamp'])


# Get the first and last timestamp of MQTT with address
def get_mqtt_first_last_timestamp_as_json_by_address(address: str):
    if not address:
        return jsonify(first=None, last=None)
    first = db.session.query(Mqtt).filter_by(topic=address).first()
    last = db.session.query(Mqtt).filter_by(topic=address).order_by(
        Mqtt.id.desc()).first()

    if first is None or last is None:
        return jsonify(first=None, last=None)
    return jsonify(first=first.timestamp, last=last.timestamp)


# Get the first and last timestamp of MQTT by topic_id
def get_mqtt_first_last_timestamp_as_json_by_id(topic_id: int):
    if not topic_id:
        return jsonify(first=None, last=None)
    first = db.session.query(Mqtt).filter_by(topic_id=topic_id).first()
    last = db.session.query(Mqtt).filter_by(topic_id=topic_id).order_by(
        Mqtt.id.desc()).first()

    if first is None or last is None:
        return jsonify(first=None, last=None)
    return jsonify(first=first.timestamp, last=last.timestamp)


# Converts 'single data_type' data to numeric DF and returns it as a line figure
def convert_single_data_type_data_to_fig(
        df_records: pd.DataFrame) -> go.Figure:
    df_records['value'] = pd.to_numeric(df_records['value'], errors='coerce')
    return px.line(df_records,
                   x='timestamp',
                   y='value',
                   template='plotly_dark')


# Converts 'json data_type' data to numeric DF, and returns it as a fig
def convert_json_data_to_fig(df_records: pd.DataFrame, columns) -> go.Figure:
    df_rows = df_records['value'].str.split(',').explode()
    df_reshaped = pd.DataFrame(
        np.reshape(df_rows.values, (df_records.shape[0], len(columns))))
    df_reshaped.columns = columns
    df_reshaped[columns] = df_reshaped[columns].apply(pd.to_numeric,
                                                      errors='coerce')
    df_reshaped['timestamp'] = pd.to_datetime(df_records['timestamp'].values)

    return px.line(df_reshaped,
                   x='timestamp',
                   y=columns,
                   template='plotly_dark')


# Converts 'json_lab data_type' data to numeric DF, and returns it as a fig
def convert_json_lab_data_to_fig(df_records: pd.DataFrame,
                                 columns) -> go.Figure:
    df_rows = df_records['value'].apply(lambda x: json.loads(x))
    df_rows = pd.DataFrame.from_records(df_rows.values, columns=columns)
    df_rows['analogueChannels'] = df_rows['analogueChannels'].explode(
        'analogueChannels')

    df_rows[columns] = df_rows[columns].apply(pd.to_numeric, errors='coerce')
    df_rows['timestamp'] = pd.to_datetime(df_records['timestamp'].values)

    return px.line(df_rows,
                   x='timestamp',
                   y=['airHum', 'airTemp', 'analogueChannels'],
                   template='plotly_dark')


# Compose an email with recipients, a title, and a message.
def create_email(title: str, message: str, recipients=None) -> Message:
    if recipients is None:
        recipients = current_app.config['MAIL_USERNAME'] or [
            'iiotdigitme@outlook.com'
        ]
    return Message(subject=title,
                   recipients=recipients,
                   body=message,
                   sender=current_app.config['MAIL_USERNAME']
                   or "iiotdigitme@outlook.com")


# Create a new thread and try to send an email
def send_email_thread(my_email_instance: Mail, email_message: Message,
                      app_ctx) -> bool:

    def send_email(my_email_message, app):
        if app:
            with app.app_context():
                try:
                    my_email_instance.send(my_email_message)
                except Exception as e:
                    app.logger.error(e)
                    app.logger.error(traceback.format_exc())
                    print(e)
                    print(traceback.format_exc())
        else:
            try:
                my_email_instance.send(my_email_message)
            except Exception as e:
                current_app.logger.error(e)
                current_app.logger.error(traceback.format_exc())
                print(e)
                print(traceback.format_exc())

    if app_ctx:
        app = app_ctx._get_current_object()
        thread = Thread(name='mail_sender',
                        target=send_email,
                        args=(email_message, app))
    else:
        thread = Thread(name='mail_sender',
                        target=send_email,
                        args=(email_message, False))
    thread.start()
    return True


# Broadcast Notification/Alert log using socketio
def broadcast_notification_socketio(notification: NotificationLog):
    if notification.notification_alert_id is None:
        url = None
        notification_alert = None
    else:
        url = f'/alerts/{notification.alert_rule.id}/logs/1'
        notification_alert = notification.alert_rule

    socketio.emit('notification', {
        'id': notification.id,
        'message': notification.message,
        'timestamp': str(notification.timestamp),
        'address': notification.address,
        'url': url,
        'notification_alert': str(notification_alert),
        'rule_id': str(f'#{str(notification.alert_rule.id)}'),
        'topic_id': notification.alert_rule.topic_id
    },
                  broadcast=True)


def broadcast_json_data(json_data: str, topic_id: Union[int, str],
                        address: str, timestamp: str):
    socketio.emit(
        'json_data', {
            'json_data': json_data,
            'address': address,
            'timestamp': timestamp,
            'topic_id': topic_id,
        })


# Broadcast json_lab dat using socketio
def broadcast_json_lab_data(json_data: str, address: str, timestamp: str,
                            topic_id: Union[int, str]):
    socketio.emit('json_lab_data', {
        'json_data': json_data,
        'address': address,
        'timestamp': timestamp,
        'topic_id': topic_id
    },
                  broadcast=True)


# Socketio
@socketio.on('message')
def handle_message(message):
    if valid_address := TopicSubscription.query.filter(
            TopicSubscription.address == message['data']['address']).first():
        if value := Mqtt.query.filter_by(topic=valid_address.address).order_by(
                Mqtt.id.desc()).first():
            emit('message', {
                'address': valid_address.address,
                'data': value.value
            })
        else:
            emit('message', {'address': valid_address.address, 'data': 0})
    emit('no data', {'data': 0})


@socketio.on('connect')
def handle_connect():
    emit('Connected', {'data': 'Connected'})


@socketio.on('disconnect')
def handle_disconnect():
    return None


# Adds notification log to the DB and broadcasts it using socketio
def create_notification_log(message: str, timestamp: datetime.datetime,
                            address: str, created_on: datetime.datetime,
                            updated_on: datetime.datetime,
                            notification_alert_id: int):
    timestamp = timestamp.replace(tzinfo=datetime.timezone.utc)
    notification_log = NotificationLog(
        message=message,
        timestamp=timestamp,
        address=address,
        created_on=created_on,
        updated_on=updated_on,
        notification_alert_id=notification_alert_id)
    db.session.add(notification_log)
    db.session.commit()
    broadcast_notification_socketio(notification_log)


# Send notification alert to email
def check_email_alert(alert: AlertRule, last_alert_seconds_ago: float,
                      cooldown: int, txt: str):
    if alert.notify_by_email and last_alert_seconds_ago > cooldown and current_app.config[
            'MAIL_ENABLED']:
        if alert.email is None:
            send_email_thread(myemail, create_email(txt, txt), current_app)
        else:
            send_email_thread(myemail,
                              create_email(txt, txt, recipients=[alert.email]),
                              current_app)


# Check if the alert has been raised. If yes, create a notification log and send an email.
def check_alert(val: str,
                alert: AlertRule,
                timestamp: datetime.datetime,
                topic_address: str,
                last_alert_seconds_ago: float,
                cooldown=360,
                column=None):
    if check_rule_operator(alert.rule, float(val), alert.rule_value):
        txt = f'Alert! {column or "Value"} {float(val)} {alert.rule} {alert.rule_value}'

        if not alert.raised:
            set_alert_raised_flag(alert, True)
            create_notification_log(message=txt,
                                    timestamp=timestamp,
                                    address=topic_address,
                                    created_on=timestamp,
                                    updated_on=timestamp,
                                    notification_alert_id=alert.id)
            check_email_alert(alert, last_alert_seconds_ago, cooldown, txt)
        return True
    if alert.raised:
        set_alert_raised_flag(alert, False)
        return False


# Set the alert raised flag
def set_alert_raised_flag(alert: AlertRule, raised: bool):
    alert.raised = raised
    db.session.merge(alert)
    db.session.commit()


# Store single data type MQTT record in the database
def store_single_mqtt_record(topic_subscription: TopicSubscription, val: float,
                             timestamp: datetime.datetime):
    if is_float(val):
        return store_mqtt_record(topic_subscription, val, timestamp)
    current_app.logger.warning('Could not parse data!')
    return False


# Store json data type MQTT record in the database
def store_json_mqtt_record(topic_subscription: TopicSubscription, json_obj):
    json_value = get_json_value(topic_subscription, json_obj)
    timestamp = get_json_timestamp(json_obj)

    return store_mqtt_record(topic_subscription, json_value, timestamp)

def get_json_timestamp(json_obj):
    timestamp = datetime.datetime.now(datetime.timezone.utc)

    if json_obj['timestamp'] is None or json_obj['timestamp'] == 'N/A' or json_obj['timestamp'] == '':
        return timestamp
        
    try:
        timestamp = set_tz_utc_if_none(
                datetime.datetime.strptime(json_obj['timestamp'],
                                        "%Y-%m-%dT%H:%M:%S.%f%zZ").astimezone(
                                            datetime.timezone.utc))
        return timestamp
    except ValueError as ve:
        current_app.logger.exception(ve)
    return timestamp    


def get_json_value(topic_subscription: TopicSubscription, json_obj):
    if topic_subscription.columns is None:
        json_value = json_obj['value']
    else:
        # Crop quotes from string value "12.5" -> 12.5
        json_value = str(json_obj['value'])[1:-1]
    return json_value


# Returns active alerts based on their parent topic id
def get_active_alerts_by_topic_id(topic_id: int):
    cond = and_(AlertRule.topic_id == topic_id, AlertRule.active == True)
    return AlertRule.query.filter(cond).all()


# Checks the MQTT data against all the alert rules
def check_alerts(alerts: list[AlertRule],
                 topic_subscription: TopicSubscription,
                 value: Union[float, int, str], timestamp: datetime.datetime):
    for a in alerts:
        if lastAlert := NotificationLog.query.filter_by(
                address=topic_subscription.address).order_by(
                    NotificationLog.id.desc()).first():
            last_alert_seconds_ago = (timestamp -
                                      lastAlert.timestamp).total_seconds()
            check_alert(value, a, timestamp, topic_subscription.address,
                        last_alert_seconds_ago, a.email_cooldown)
        else:
            check_alert(value, a, timestamp, topic_subscription.address, 1, 0)


# Check the MQTT data with columns against all the alert rules
def check_alerts_with_columns(alerts: list[AlertRule],
                              topic_subscription: TopicSubscription,
                              value: Union[float, int, str],
                              timestamp: datetime.datetime,
                              is_dict=False):
    for a in alerts:
        col_index = json.loads(topic_subscription.columns).index(a.column)
        col_name = json.loads(topic_subscription.columns)[col_index]
        obj_value = float(value[col_name]) if is_dict else float(
            value[col_index])
        if lastAlert := NotificationLog.query.filter_by(
                notification_alert_id=a.id).order_by(
                    NotificationLog.timestamp.desc()).first():
            lastAlert.timestamp = lastAlert.timestamp.replace(
                tzinfo=datetime.timezone.utc)
            last_alert_seconds_ago = (timestamp -
                                      lastAlert.timestamp).total_seconds()
            check_alert(obj_value, a, timestamp, topic_subscription.address,
                        last_alert_seconds_ago, a.email_cooldown, col_name)
        else:
            check_alert(obj_value, a, timestamp, topic_subscription.address, 1,
                        0, col_name)
