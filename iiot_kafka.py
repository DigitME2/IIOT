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
from typing import List

import pandas as pd
import sqlalchemy as sqldb
from confluent_kafka import Producer
from sqlalchemy import and_, select
from sqlalchemy.orm import sessionmaker

from app.models import AlertRule, Mqtt, NotificationLog, TopicSubscription, db
from config import Config

c = Config()

KAFKA_TOPIC_IIOT = 'iiot'
KAFKA_TOPIC_SENSORS = 'iiot.sensors'
KAFKA_TOPIC_SENSOR_DATA = 'iiot.sensor.data'

BOOTSTRAP_SERVERS = '192.168.0.145:9092'

producer = Producer({'bootstrap.servers': BOOTSTRAP_SERVERS})


def sensors_definition_to_kafka(session: sessionmaker):
    try:
        subs = session.query(TopicSubscription).all()
    except Exception as e:
        print(e)
    return subs


def get_sensor_data(session: sessionmaker, topic_id: int):
    '''Returns the sensor data from the database based on topic id.
       If exception is raised, it will print the exception message'''
    try:
        mqtt_data = session.query(Mqtt).order_by(
            Mqtt.id.desc()).filter(Mqtt.topic_id == topic_id).first()
    except Exception as e:
        print(e)
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
def need_partition(sensors_data: List):
    if sys.getsizeof(sensors_data) >= 1024*1024:
        print('Data > 1MB')
        # Partition..


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
    # engine = sqldb.create_engine('instane///' + c.SQLALCHEMY_DATABASE_URI)
    engine = sqldb.create_engine('sqlite:///instance/data.sqlite')
    connection = engine.connect()
    metadata = sqldb.MetaData()

    Session = sessionmaker(bind=engine)
    session = Session()

    sensor_def = sensors_definition_to_kafka(session)
    print(sensor_def)
    sd_arr = get_sensor_data_between_timestamp(session, 20,
                                               datetime.datetime.now() - datetime.timedelta(hours=1), datetime.datetime.now())
    sd_arr_dict = sensors_data_to_dict(sd_arr)

    sd_arr_dict_json = [json.dumps(s) for s in sd_arr_dict]
    print(len(sd_arr_dict_json))

    '''
    # 20 is the topic_id of lab/esp32/BMP180
    for s in sensor_def:
        # print(s)
        sd = get_sensor_data(session, s.id)
        if sd is None:
            continue
        sd_json = json.dumps(sd.to_dict())
        print(sd_json)
        print(len(sd_json))
    '''
    sch1 = datetime.datetime.now()
    sch2 = datetime.datetime.now()
    every_minute = datetime.datetime.now()

    # Get the sensors definitions (Topic Subscriptions)
    sensor_def = sensors_definition_to_kafka(session)

    while True:
        # producer.pool(1.0)
        producer.poll(10.0)
        try:
            current_time = datetime.datetime.now()

            # Send sensor data every minute through Kafka
            if current_time > every_minute:
                print('every_minute')
                every_minute = current_time + datetime.timedelta(minutes=1)
                date_from = datetime.datetime.now().replace(second=0, microsecond=0) - \
                    datetime.timedelta(minutes=1)

                date_to = date_from + \
                    datetime.timedelta(minutes=1, microseconds=-1)

                print(f'Getting data from {str(date_from)} to {str(date_to)}')
 
                # Get the Sensor Data from every Topic Subscription
                # *Perhaphs better (faster) option would be: getting all the MQTT data between the timestamps
                for ts in sensor_def:
                    sd_arr = get_sensor_data_between_timestamp(session, ts.id, date_from, date_to)
                    sd_arr_dict = sensors_data_to_dict(sd_arr)
                    sd_arr_dict_json = [json.dumps(s) for s in sd_arr_dict]
                    for i, s in enumerate(sd_arr_dict_json):
                        producer.produce(topic=KAFKA_TOPIC_SENSOR_DATA,
                                     key=f"{sd_arr[i].id}{sd_arr[i].timestamp}",
                                     value=s,
                                     on_delivery=delivery_report)

                # Test - Getting MQTT data from single Topic Subscription
                # sd_arr = get_sensor_data_between_timestamp(
                #     session, 20, date_from, date_to)
                # sd_arr_dict = sensors_data_to_dict(sd_arr)
                # sd_arr_dict_json = [json.dumps(s) for s in sd_arr_dict]

                # for i, s in enumerate(sd_arr_dict_json):
                #     producer.produce(topic=KAFKA_TOPIC_SENSOR_DATA,
                #                      key=f"{sd_arr[i].id}{sd_arr[i].timestamp}",
                #                      value=s,
                #                      on_delivery=delivery_report)

            if current_time > sch1:
                print('sch1')
                sch1 = current_time + datetime.timedelta(minutes=60)
                sensor_def = sensors_definition_to_kafka(session)
                sensor_sef = [x.to_dict() for x in sensor_def]
                print(f'sensor definition: ({sys.getsizeof(json.dumps(sensor_sef))})')
                producer.produce(topic=KAFKA_TOPIC_SENSORS, key="Sensors", value=json.dumps(
                    sensor_sef), on_delivery=delivery_report)

            '''
            if current_time > sch2:
                print('sch2')
                sch2 = current_time + datetime.timedelta(seconds=5)
                sd = get_sensor_data(session, 20)

                producer.produce(topic=KAFKA_TOPIC_SENSOR_DATA,
                                key=f"{sd.id}{sd.timestamp}",
                                value=sd.value,
                                on_delivery=delivery_report)
            '''
        except KeyboardInterrupt:
            print('KeyboardInterrupt!')
            break

    print('\nFlushing records...')
    producer.flush()
