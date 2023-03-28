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
import os


class Config(object):
    # Flask
    SECRET_KEY = os.environ.get(
        "SECRET_KEY") or "xRPiSTZuWUT0L2VDspYSUpNMbRi2ta8hsdf"
    FLASK_APP = os.environ.get("FLASK_APP")
    FLASK_ENV = os.environ.get('FLASK_ENV') or 'production'
    ENV = os.environ.get('ENV') or 'production'
    DEBUG = os.environ.get("DEBUG") or False
    TEMPLATES_AUTO_RELOAD = os.environ.get("TEMPLATES_AUTO_RELOAD") or True
    PRINT_REQUEST_PROCESS_TIME = os.environ.get(
        "PRINT_REQUEST_PROCESS_TIME") or False
    TESTING = False

    # SQLAlchemy Database
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_DATABASE_URI = "sqlite:///data.sqlite"

    # EMAIL
    MAIL_SERVER = "smtp-mail.outlook.com"
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USE_SSL = False
    MAIL_DEBUG = False
    MAIL_USERNAME = "iiotdigitme@outlook.com"
    MAIL_PASSWORD = "mcehminpmwzunvss"
    MAIL_DEFAULT_SENDER = None
    MAIL_MAX_EMAILS = None
    MAIL_ENABLED = True
    # MAIL_SUPPRESS_SEND = app.testing
    # MAIL_ASCII_ATTACHMENTS = False

    # GEVENT
    GEVENT_SUPPORT = os.environ.get("GEVENT_SUPPORT") or False

    # FOR TEMPLATES
    TOPICS_PER_PAGE = 50

    # MQTT SPECIFIC
    # MQTT_URL = "10.30.47.12"
    MQTT_URL = "127.0.0.1"
    MQTT_TOPIC_PING_DEVICES = "esp32config/PING"
    MQTT_TOPIC_PING_RESPONSE_DEVICES = "dm2/devices"

    # DASH
    DASH_UPDATE_INTERVAL = 15000


class TestConfig(object):
    # Flask
    SECRET_KEY = os.environ.get(
        "SECRET_KEY") or "xRPiSTZuWUT0L2VDspYSUpNMbRi2ta8hsdf"
    FLASK_APP = os.environ.get("FLASK_APP")
    FLASK_ENV = os.environ.get("FLASK_ENV") or "production"
    ENV = os.environ.get("ENV") or "production"
    DEBUG = os.environ.get("DEBUG") or False
    TEMPLATES_AUTO_RELOAD = os.environ.get("TEMPLATES_AUTO_RELOAD") or False
    PRINT_REQUEST_PROCESS_TIME = os.environ.get(
        "PRINT_REQUEST_PROCESS_TIME") or False
    SERVER_NAME = os.environ.get("SERVER_NAME") or "127.0.0.1:5000"
    # SERVER_NAME     = os.environ.get('SERVER_NAME') or '0.0.0.0:80'
    TESTING = True
    PRESERVE_CONTEXT_ON_EXCEPTION = True

    # SQLAlchemy Database
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_DATABASE_URI = "sqlite:///testdb.sqlite"

    # EMAIL
    MAIL_SERVER = "smtp-mail.outlook.com"
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USE_SSL = False
    MAIL_DEBUG = False
    MAIL_USERNAME = "iiotdigitme@outlook.com"
    MAIL_PASSWORD = "mcehminpmwzunvss"
    MAIL_DEFAULT_SENDER = None
    MAIL_MAX_EMAILS = None
    MAIL_ENABLED = False
    # MAIL_SUPPRESS_SEND = app.testing
    # MAIL_ASCII_ATTACHMENTS = False

    # GEVENT
    GEVENT_SUPPORT = os.environ.get("GEVENT_SUPPORT") or True

    # FOR TEMPLATES
    TOPICS_PER_PAGE = 50

    # MQTT SPECIFIC
    MQTT_URL = "127.0.0.1"
    MQTT_TOPIC_PING_DEVICES = "esp32config/PING"
    MQTT_TOPIC_PING_RESPONSE_DEVICES = "dm2/devices"

    # DASH
    DASH_UPDATE_INTERVAL = 15000