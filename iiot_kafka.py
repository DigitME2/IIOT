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
import sys
import time
import logging
import math
from typing import List

import pandas as pd
import sqlalchemy as sqldb
from confluent_kafka import Producer
from sqlalchemy import and_, select
from sqlalchemy.orm import sessionmaker

from app.models import AlertRule, Mqtt, NotificationLog, TopicSubscription, db
from config import Config

logging.basicConfig(level=logging.DEBUG, 
					format="%(asctime)s - [%(levelname)s] - %(message)s", 
					handlers=[
						logging.FileHandler("kafka_log.log"),
						logging.StreamHandler()
						]
					)
c = Config()

KAFKA_TOPIC_IIOT = 'iiot'
KAFKA_TOPIC_SENSORS = 'iiot.sensors'
KAFKA_TOPIC_SENSOR_DATA = 'iiot.sensor.data'

KAFKA_ALERT_RULES = 'iiot.sensors.alert_rules'
KAFKA_ALERT_LOGS = 'iiot.sensors.alert_rules.logs'


BOOTSTRAP_SERVERS = '10.30.47.12:9092'

producer = Producer({'bootstrap.servers': BOOTSTRAP_SERVERS})

def get_notification_log_between_timestamp(session: sessionmaker, dt_from: datetime.datetime, dt_to: datetime.datetime):
    cond = NotificationLog.timestamp.between(str(dt_from), str(dt_to))
    return session.query(NotificationLog).filter(cond).all()

def get_topic_subscriptions(session: sessionmaker):
    try:
        subs = session.query(TopicSubscription).all()
    except Exception as e:
        logging.exception(e)
    return subs


def get_topic_subscriptions_between_timestamp(session: sessionmaker, dt_from: datetime.datetime, dt_to: datetime.datetime):
    '''Returns the Topic Subscription (Sensor Definition) data between the specified date and time.'''

    cond = TopicSubscription.updated_on.between(str(dt_from), str(dt_to))
    return session.query(TopicSubscription).filter(cond).all()


def get_sensor_data(session: sessionmaker, topic_id: int):
    '''Returns the sensor data from the database based on topic id.
       If exception is raised, it will print the exception message'''
    try:
        mqtt_data = session.query(Mqtt).order_by(
            Mqtt.id.desc()).filter(Mqtt.topic_id == topic_id).first()
    except Exception as e:
        logging.exception(e)
    return mqtt_data


def get_sensor_data_between_timestamp(session: sessionmaker, topic_id: int, dt_from: datetime.datetime, dt_to: datetime.datetime):
    '''Gets the sensor data between the specified date and time based on topic id.'''
    cond = and_(Mqtt.timestamp.between(
        str(dt_from), str(dt_to)), Mqtt.topic_id == topic_id)
    return session.query(Mqtt).with_entities(Mqtt.id, Mqtt.topic, Mqtt.value, Mqtt.timestamp, Mqtt.topic_id).filter(cond).all()


def sensors_data_to_dict(sensors_data_list: List[Mqtt]):
    '''Converts the list of sensor data into a dictionary.'''
    return [sensor_data_to_dict(s) for s in sensors_data_list]


def sensor_data_to_dict(sensor_data: Mqtt):
    '''Converts the sensor data into a dictionary.
       Timestamp is converted into isoformat.'''
    return dict(
        id=sensor_data.id,
        topic=sensor_data.topic,
        value=sensor_data.value,
        timestamp=sensor_data.timestamp.isoformat(),
        topic_id=sensor_data.topic_id
    )


# Kafka limits message size to 1MB (1024*1024 bytes), therefore we need to partition sensor data if it's larger than 1MB
# I leave the safety margin and slice the data by 512*1024 bytes
def need_partition(sensors_data: List, partition_size=512*1024):
    if len(sensors_data) == 0:
        return False, sensors_data
    # Get Biggest Byte Size Element from the list
    max_bytes = 0
    for x in sensors_data:
        max_bytes = max(sys.getsizeof(x), max_bytes)

    # The Total (Maximum Possible) Byte Size of the list
    number_of_elements = len(sensors_data)
    total_size_in_bytes = max_bytes*number_of_elements

    # Number of partitions
    partitions = math.ceil(total_size_in_bytes / partition_size)

    # Size of the slice
    slice_size = math.floor(partition_size / max_bytes)

    if total_size_in_bytes >= partition_size:
        partitioned_sensors_data = [
            sensors_data[(p - 1) * slice_size:p * slice_size]
            for p in range(1, partitions + 1)
        ]
        return (True, partitioned_sensors_data)
    return (False, sensors_data)

def delivery_report(err, msg):
    """
    Reports the success or failure of a message delivery.
    Args:
        err (KafkaError): The error that occurred on None on success.
        msg (Message): The message that was produced or failed.
    """

    if err is not None:
        print(f"Delivery failed for Key {msg.key()} : {err}")
        return
    #print(f'Key {msg.key()} successfully produced topic: {msg.topic()} partition: [{msg.partition()}] offset: {msg.offset()}')


if __name__ == '__main__':
    print('main')
    engine = sqldb.create_engine('sqlite:///instance/data.sqlite')
    connection = engine.connect()
    metadata = sqldb.MetaData()

    Session = sessionmaker(bind=engine)
    session = Session()

    every_minute2 = datetime.datetime.now()
    sch2 = datetime.datetime.now()
    every_minute = datetime.datetime.now()

    while True:
        producer.poll(10.0)
        try:
            current_time = datetime.datetime.now()

            # Send the snensor (MQTT) data every minute through Kafka
            if current_time > every_minute:
                every_minute = current_time + datetime.timedelta(minutes=1)
                date_from = datetime.datetime.now().replace(second=0, microsecond=0) - \
                    datetime.timedelta(minutes=1)

                date_to = date_from + \
                    datetime.timedelta(minutes=1, microseconds=-1)

                print(f'Getting MQTT data from {str(date_from)} to {str(date_to)}')

                # Get the sensors definitions (Topic Subscriptions)
                topic_subs = get_topic_subscriptions(session)
                
                # Get the Sensor Data from every Topic Subscription
                # *Perhaphs better (faster) option would be: getting all the MQTT data between the timestamps
                for ts in topic_subs:
                    sd_arr = get_sensor_data_between_timestamp(session, ts.id, date_from, date_to)
                    sd_arr_dict = sensors_data_to_dict(sd_arr)
                    partitioned_data = need_partition(sd_arr_dict, 1024*512)
                    if partitioned_data[0]:
                        for p in partitioned_data[1]:
                            sd_arr_dict_json = [json.dumps(s) for s in p]
                            for i, s in enumerate(sd_arr_dict_json):
                                print(f"{p[i]['id']}_{p[i]['topic_id']}_{p[i]['timestamp']}")
                                producer.produce(topic=KAFKA_TOPIC_SENSOR_DATA,
                                            key=f"{p[i]['id']}_{p[i]['topic_id']}_{p[i]['timestamp']}",
                                            value=s,
                                            on_delivery=delivery_report)
                    else:
                        sd_arr_dict_json = [json.dumps(s) for s in partitioned_data[1]]
                        for i, s in enumerate(sd_arr_dict_json):
                            print(f"{partitioned_data[1][i]['id']}_{partitioned_data[1][i]['topic_id']}_{partitioned_data[1][i]['timestamp']}")
                            producer.produce(topic=KAFKA_TOPIC_SENSOR_DATA,
                                        key=f"{partitioned_data[1][i]['id']}_{partitioned_data[1][i]['topic_id']}_{partitioned_data[1][i]['timestamp']}",
                                        value=s,
                                        on_delivery=delivery_report)

            if current_time > every_minute2:
                every_minute2 = current_time + datetime.timedelta(minutes=1)
                date_from = datetime.datetime.now().replace(second=0, microsecond=0) - \
                    datetime.timedelta(minutes=1)
                date_to = date_from + \
                    datetime.timedelta(minutes=1, microseconds=-1)

                print(f'Getting Topic Subscription data from {str(date_from)} to {str(date_to)}')

                # Get Topic Subscriptions
                topic_subs = get_topic_subscriptions_between_timestamp(session, date_from, date_to)
                topic_subs_dict = [x.to_dict() for x in topic_subs]

                print(topic_subs_dict)

                # Produce Topic Subscriptions
                producer.produce(topic=KAFKA_TOPIC_SENSORS, key="Sensors", value=json.dumps(
                    topic_subs_dict), on_delivery=delivery_report)

                print(f'Getting Notification Logs data from {str(date_from)} to {str(date_to)}')

                # Get Notification Logs
                notification_logs = get_notification_log_between_timestamp(session, date_from, date_to)
                notification_logs_dict = [x.to_dict() for x in notification_logs]
                
                print(notification_logs_dict)
                # Produce Notification Logs
                producer.produce(topic=KAFKA_ALERT_LOGS, key="NotificationLogs", value=json.dumps(
                    notification_logs_dict), on_delivery=delivery_report)

        except Exception as e:
            logging.exception(e)
        


