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
import asyncio
import os
import re
import random
import paho.mqtt.client as mqtt_client
import pandas as pd
import plotly
from flask import (Blueprint, abort, current_app, flash, g, jsonify, redirect,
                   render_template, request, send_from_directory, url_for)
from paho import mqtt
from sqlalchemy import and_, bindparam, text

from app.models import (AlertCompOperators, AlertFunctions, AlertRule,
                        DataTypes, Mqtt, NotificationLog, TopicSubscription,
                        db)
from app.util import *

from . import (broadcast_json_lab_data, broadcast_notification_socketio,
               convert_json_data_to_fig, convert_json_lab_data_to_fig,
               convert_single_data_type_data_to_fig, create_email,
               get_file_list, get_mqtt_data_from_to_by_id,
               get_mqtt_first_last_timestamp_as_json_by_id, get_topics_graph,
               mqttc, send_email_thread, myemail, update_g_varaible, timerBulkSave)

main_blueprint = Blueprint("main_blueprint", __name__)


@main_blueprint.route("/")
@main_blueprint.route("/<int:page>")
def home(page=1):
    """Landing page."""
    # Send the last 50 (or more/less) logs to the main page
    mylog = NotificationLog.query.order_by(NotificationLog.id.desc()).paginate(
        page=page,
        per_page=current_app.config.get("TOPICS_PER_PAGE") or 50,
        error_out=False)

    update_g_varaible(db)
    return render_template(
        "index.html",
        title="Landing Page",
        mylog=mylog,
        active_sensors=g.number_of_active_sensors,
        inactive_sensors=g.number_of_inactive_sensors,
    )


@main_blueprint.route("/favicon.ico")
def favicon():
    return send_from_directory(
        os.path.join(current_app.root_path, "static"),
        "favicon.ico",
        mimetype="image/vnd.microsoft.icon",
    )


@main_blueprint.route("/log/count", methods=["GET"])
def get_log_count():
    rows = db.session.query(NotificationLog).count()
    return jsonify({"value": rows})


@main_blueprint.route("/log/<int:id>/delete", methods=["GET", "POST"])
def delete_log(id):
    log = NotificationLog.query.filter_by(id=id).first()
    if request.method == "POST":
        if log:
            db.session.delete(log)
            db.session.commit()
            flash(f"Log #{log.id}:{log.message} deleted successfully",
                  "success")

            return redirect(url_for("main_blueprint.home"))
        abort(404)

    return render_template("alerts/logs/delete.html", log=log)

@main_blueprint.route("/log/<int:id>/delete_logs", methods=["POST"])
def delete_logs(id):
    log_ids = request.form.getlist("log_id")
    deleted_logs = []
    for log_id in log_ids:
        log = NotificationLog.query.filter_by(id=log_id).first()
        if log:
            db.session.delete(log)
            db.session.commit()
            deleted_logs.append(log.id)
        else:
            flash(f"Log with ID {log_id} was not found in the database and could not be deleted.", "error")
    if deleted_logs:
        flash(f"The following logs have been deleted: {deleted_logs}", "success")
    return redirect(url_for("main_blueprint.get_notification_logs", id=id, page=1))


@main_blueprint.route("/topics/csv/", methods=["POST"])
def get_csv_file():
    date_from = request.form.get("date_from")
    date_to = request.form.get("date_to")
    topic_id = request.form.get("topic_id")

    # Get Data between the date_from and date_to with the mqtt topic_id that matches the form topic_id
    date_to_inclusive = datetime.datetime.strptime(
        date_to, "%Y-%m-%d") + datetime.timedelta(days=1)
    cond = and_(Mqtt.timestamp.between(date_from, date_to_inclusive),
                Mqtt.topic_id == topic_id)
    csv_topic_like = Mqtt.query.filter(cond)
    with db.engine.begin() as conn:
        csv_df = pd.read_sql_query(
                sql=text(str(csv_topic_like.statement.compile(
                    compile_kwargs={"literal_binds": True}))),
                    con=conn)

    # Convert to CSV file
    resp = current_app.make_response(csv_df.to_csv())
    resp.headers["Content-Disposition"] = "attachment; filename=export.csv"
    resp.headers["Content-Type"] = "text/csv"
    return resp


@main_blueprint.route("/vis/", methods=["GET", "POST"])
def get_static_graph():
    if request.method == "POST":
        sub = request.form.get("id")
        return get_mqtt_first_last_timestamp_as_json_by_id(sub)
    else:
        subs = TopicSubscription.query.all()
        plot = request.args.get("plot") or None
        date_from = request.args.get("date_from") or None
        date_to = request.args.get("date_to") or None
        id = request.args.get("id") or None

        if plot:
            selected_sub = TopicSubscription.query.filter(
                TopicSubscription.id == id).first()
            if not selected_sub:
                return abort(404)
            # Plot single data_type
            if selected_sub.data_type == "single":
                df_records = get_mqtt_data_from_to_by_id(
                    id, date_from, date_to)
                fig_topic = convert_single_data_type_data_to_fig(df_records)
                mqtt_graph = json.dumps(fig_topic,
                                        cls=plotly.utils.PlotlyJSONEncoder)

                return render_template(
                    "dash/static_graph.html",
                    title="Static Graph",
                    subs=subs,
                    mqtt=mqtt_graph,
                )
            # Plot json data_type
            elif selected_sub.data_type == "json":
                if selected_sub.columns is None:
                    columns = ['value']
                else:
                    columns = json.loads(selected_sub.columns)
                df_records = get_mqtt_data_from_to_by_id(
                    id, date_from, date_to)
                fig_topic = convert_json_data_to_fig(df_records, columns)
                mqtt_graph = json.dumps(fig_topic,
                                        cls=plotly.utils.PlotlyJSONEncoder)

                return render_template(
                    "dash/static_graph.html",
                    title="Static Graph",
                    subs=subs,
                    mqtt=mqtt_graph,
                )
            # Plot json_lab data_type
            elif selected_sub.data_type == "json_lab":
                columns = json.loads(selected_sub.columns)
                df_records = get_mqtt_data_from_to_by_id(
                    id, date_from, date_to)
                fig_topic = convert_json_lab_data_to_fig(df_records, columns)
                mqtt_graph = json.dumps(fig_topic,
                                        cls=plotly.utils.PlotlyJSONEncoder)

                return render_template(
                    "dash/static_graph.html",
                    title="Static Graph",
                    subs=subs,
                    mqtt=mqtt_graph,
                )
            # If data_type is unknown, plot empty figure
            fig_topic = {}
            mqtt_graph = json.dumps(fig_topic,
                                    cls=plotly.utils.PlotlyJSONEncoder)
            return render_template(
                "dash/static_graph.html",
                title="Static Graph",
                subs=subs,
                mqtt=mqtt_graph,
            )

    return render_template("dash/static_graph.html",
                           title="Static Graph",
                           subs=subs)


## Alerts/Notifications


@main_blueprint.route("/alerts/", methods=["GET", "POST"])
def get_all_rules():
    subs = TopicSubscription.query.all()
    rules = AlertRule.query.all()

    return render_template(
        "alerts/rules/index.html", title="Alert Rules", subs=subs, rules=rules
    )


@main_blueprint.route("/alerts/add", methods=["GET", "POST"])
def add_rule():
    if request.method == "POST":
        selected_topic = request.form["select_topic_options"]
        selected_topic_id = request.form.get("topic_id")
        active = request.form.get("active") or 0
        notify_by_email = request.form.get("notify_by_email") or 0
        email = request.form.get("email") or None
        column = request.form.get("column") or None
        rule = request.form.get("select_comp_operators") or None
        rule_value = request.form.get("rule_value") or None

        func_checked = request.form.get("checkbox_fn") or None

        func = request.form.get("func") or None
        func_time = request.form.get("func_time") or None
        func_time_n = request.form.get("func_time_n") or None

        func_time = bool(func_time or func_time == "1")
        func_checked = bool(func_checked)
        active = bool(active)
        notify_by_email = bool(notify_by_email)

        if rule is None:
            flash(f"Missing rule!")
            return redirect(url_for("main_blueprint.get_all_rules"))

        # Check if rule exists in table AlertCompOperators. Done!
        # Valid rule operators are: '<','<=','>','>=''==','!='
        alert_comp_operators = AlertCompOperators.query.all()
        alert_comp_operators = [a.op for a in alert_comp_operators]
        if rule not in alert_comp_operators:
            flash(f"Invalid rule operator!")
            return redirect(url_for("main_blueprint.get_all_rules"))

        if rule_value is None:
            flash(f"Missing rule value!")
            return redirect(url_for("main_blueprint.get_all_rules"))

        # Check if function rule exists in table AlertFunctions. Done!
        # Valid functions are: 'Mean', 'Mode', 'Median', 'Max', 'Min', 'Standard deviation', 'Change', 'Percent change'
        if func_checked:
            alert_functions = AlertFunctions.query.all()
            alert_functions = [a.op for a in alert_functions]
            if func not in alert_functions:
                flash(f"Invalid alert function!")
                return redirect(url_for("main_blueprint.get_all_rules"))

        if not func_checked:
            func = None
            func_time = None
            func_time_n = None

        alert_rule = AlertRule(
            address=selected_topic,
            topic_id=selected_topic_id,
            rule=rule,
            rule_value=rule_value,
            active=active,
            notify_by_email=notify_by_email,
            email=email,
            column=column,
            func=func,
            func_time=func_time,
            func_time_n=func_time_n,
        )

        old_alert_rule = AlertRule.query.filter(
            and_(
                AlertRule.rule == rule,
                and_(AlertRule.topic_id == selected_topic_id,
                     AlertRule.column == column),
            )).first()
        if old_alert_rule:
            old_alert_rule.active = active
            old_alert_rule.rule_value = rule_value

            db.session.merge(old_alert_rule)
            db.session.commit()
            flash(f"Rule {selected_topic} has been updated", "success")
        else:
            db.session.add(alert_rule)
            db.session.commit()
            flash(f"Rule {selected_topic} has been added", "success")

        return redirect(url_for("main_blueprint.get_all_rules"))
    else:
        subs = TopicSubscription.query.all()
        comp_operators = AlertCompOperators.query.all()
        alert_functions = AlertFunctions.query.all()
        rules = AlertRule.query.all()

    return render_template(
        "alerts/rules/addRule.html",
        title="Add Alert Rule",
        subs=subs,
        rules=rules,
        alert_functions=alert_functions,
        comp_operators=comp_operators,
    )


@main_blueprint.route("/alerts/<int:id>/edit", methods=["GET", "POST"])
def edit_rule(id=-1):
    comp_operators = AlertCompOperators.query.all()
    alert_functions = AlertFunctions.query.all()
    rule = AlertRule.query.filter_by(id=id).first()
    if request.method == "POST":
        if rule:
            active = request.form.get("active") or 0
            raised = request.form.get("raised") or 0
            notify_by_email = request.form.get("notify_by_email") or 0
            email = request.form.get("email") or None
            email_cooldown = request.form.get("email_cooldown") or 0
            r = request.form.get("select_comp_operators") or None
            rule_value = request.form.get("rule_value") or None

            active = bool(active)
            notify_by_email = bool(notify_by_email)
            raised = bool(raised)

            rule.active = active
            rule.notify_by_email = notify_by_email
            rule.rule = r
            rule.rule_value = rule_value
            rule.email = email
            rule.email_cooldown = email_cooldown
            rule.raised = raised

            db.session.merge(rule)
            db.session.commit()
            if rule.column is None:
                flash(f"Rule {rule.rule} has been updated", "success")
            else:
                flash(f"Rule {rule.rule} {rule.column} has been updated",
                      "success")

            return redirect(url_for("main_blueprint.get_all_rules"))
        abort(404)
    return render_template(
        "alerts/rules/edit.html",
        title="Edit Alert Rule",
        rule=rule,
        comp_operators=comp_operators,
        alert_functions=alert_functions,
    )


@main_blueprint.route("/alerts/<int:id>/delete", methods=["GET", "POST"])
def delete_rule(id):
    rule = AlertRule.query.filter_by(id=id).first()
    if request.method == "POST":
        if rule:
            db.session.delete(rule)
            db.session.commit()
            rule_column = rule.column or "value"
            flash(
                f"Rule #{rule.id} {rule_column}{rule.rule}{rule.rule_value} deleted successfully",
                "success",
            )

            return redirect(url_for("main_blueprint.get_all_rules"))
        abort(404)

    return render_template("alerts/rules/delete.html", rule=rule)


@main_blueprint.route("/alerts/<int:id>/", methods=["GET", "POST"])
def get_notification(id=-1):
    notification = AlertRule.query.filter_by(id=id).first()
    logs = request.args.get("logs")
    if notification:
        if not logs:
            notification.notification_logs = []
        return jsonify(notification)
    return abort(404)


@main_blueprint.route("/alerts/<int:id>/logs/<int:page>", methods=["GET"])
def get_notification_logs(id, page=1):
    notification_logs = NotificationLog.query.filter_by(
        notification_alert_id=id).paginate(
            page=page,
            per_page=current_app.config.get("TOPICS_PER_PAGE") or 50,
            error_out=False)
    return render_template(
        "alerts/logs/list.html",
        id = id,
        title=f"Alert {id} Log List",
        notification_logs=notification_logs,
    )


## Subscriptions


@main_blueprint.route("/subs/", methods=["GET", "POST"])
def get_all_subs():
    if (request.method == "GET" and request.args.get("topic")
            and request.args.get("data_type")) or request.method == "POST":
        if request.content_type == "application/x-www-form-urlencoded":
            address = request.form["address"]
            data_type = request.form["select_data_types"]
            columns = request.form.get("columns") or None
        else:
            address = request.args.get("topic")
            data_type = request.args.get("data_type")
            columns = request.args.get("columns") or None

        subscription = TopicSubscription(address=address,
                                         data_type=data_type,
                                         columns=columns)
        subscription.graph = True

        # Validate address
        if address is None or len(address) <= 1:
            flash("Topic address is too short!", "warning")
            return redirect(url_for("main_blueprint.get_all_subs"))
        elif not re.match(r"^(\d|\w|\/)+$", address):
            flash("Topic address can only contain letters, numbers, underscore and forward slashes (/). No spaces or other special characters.", "warning")
            return redirect(url_for("main_blueprint.get_all_subs"))


        # Validate column names
        if data_type == 'json' or data_type == 'json_lab':
            if columns is None or not re.match(r'^\["\w+"(?:,\s*"\w+")*\]|^\[""\]|\[\]$', columns):
                flash('The columns must be surrounded by [], each column must be quoted and separated by comma. E.g ["Temperature", "Humidity"] or ["Temperature"]')
                return redirect(url_for("main_blueprint.get_all_subs"))

        if TopicSubscription.query.filter(
                TopicSubscription.address == address).filter(
                    TopicSubscription.deleted == False).first():
            flash("Topic already exists!", "warning")
            return redirect(url_for("main_blueprint.get_all_subs"))

        try:
            db.session.add(subscription)
            db.session.commit()
        except Exception as e:
            current_app.logger.exception(e)
            flash(f"Could not add subscription {address}")
            return redirect(url_for("main_blueprint.get_all_subs"))

        flash("Subscription added", "success")
        return redirect(url_for("main_blueprint.get_all_subs"))
    else:
        subs = TopicSubscription.query.all()
        select_data_types = DataTypes.query.all()

    return render_template(
        "subs/list.html",
        subs=subs,
        select_data_types=select_data_types,
        title="Topic Subscriptions",
    )


@main_blueprint.route("/subs/<int:id>/edit", methods=["GET", "POST"])
def edit_sub(id=-1):
    subscription = TopicSubscription.query.filter_by(id=id).first()
    if not subscription:
        abort(404, description=f"Subscription with id {id} not found!")
    if request.method == "POST":
        subscribe = request.form.get("subscribe") or 0
        high_freq = request.form.get("high_freq") or 0

        high_freq = bool(high_freq)
        subscribe = bool(subscribe)

        subscription.high_freq = high_freq
        subscription.graph = True

        if subscription.subscribe != subscribe:
            subscription.subscribe = subscribe
            with current_app.app_context():
                if subscription.subscribe:
                    res_mid = mqttc.subscribe(subscription.address)
                else:
                    res_mid = mqttc.unsubscribe(subscription.address)

            if res_mid[0] != mqtt.client.MQTT_ERR_SUCCESS:
                flash(f"Error: {res_mid[0]}", "error")
                return redirect(url_for("main_blueprint.get_all_subs"))

        db.session.merge(subscription)
        db.session.commit()

        update_g_varaible(db)

        flash(
            f"Subscription {subscription.id} {subscription.address} has been updated",
            "success",
        )
        return redirect(url_for("main_blueprint.get_all_subs"))
    return render_template("/subs/edit.html",
                           title="Edit Topic Subscription",
                           subscription=subscription)


@main_blueprint.route("/subs/<int:id>", methods=["POST", "GET"])
def get_sub(id):
    if subscription := TopicSubscription.query.filter_by(id=id).first():
        return jsonify(subscription)
    return ""


@main_blueprint.route("/subs/<int:id>/logs/<int:page>", methods=["GET"])
def get_sub_mqtt_logs(id, page=1):
    subscription = TopicSubscription.query.filter_by(id=id).first()
    if subscription:
        mqtt_data = (Mqtt.query.order_by(
            Mqtt.id.desc()).filter_by(topic_id=subscription.id).paginate(
                page=page,
                per_page=current_app.config.get("TOPICS_PER_PAGE") or 50,
                error_out=False))

    return render_template(
        "topics/list.html",
        id=id,
        topics=mqtt_data,
        title=f"MQTT Data {subscription.address}",
    )


@main_blueprint.route("/subs/<int:id>/delete", methods=["GET", "POST"])
def delete_sub(id):
    topic = TopicSubscription.query.filter_by(id=id).first()
    if request.method == "POST":
        if topic:
            """
            returns a tuple (result, mid), where result is MQTT_ERR_SUCCESS
            to indicate success or (MQTT_ERR_NO_CONN, None) if the client
            is not currently connected. mid is the message ID for the unsubscribe
            request. The mid value can be used to track the unsubscribe request
            by checking against the mid argument in the on_unsubscribe() callback if it is defined.
            """
            if len(topic.address) != 0:
                res_mid = mqttc.unsubscribe(topic.address)
            else:
                topic.subscribe = False
                topic.deleted = True
                db.session.merge(topic)
                db.session.commit()

                update_g_varaible(db)

                flash(
                    f"Subscription #{topic.id}:{topic.address} deleted successfully",
                    "success",
                )
                return redirect(url_for("main_blueprint.get_all_subs"))

            if res_mid[0] == mqtt.client.MQTT_ERR_SUCCESS:
                topic.subscribe = False
                topic.deleted = True
                db.session.merge(topic)
                db.session.commit()

                update_g_varaible(db)

                flash(
                    f"Subscription #{topic.id}:{topic.address} deleted successfully",
                    "success",
                )
            else:
                flash(f"Error: {res_mid[0]}", "error")

            return redirect(url_for("main_blueprint.get_all_subs"))
        abort(404)

    return render_template("subs/delete.html", topic=topic)


@main_blueprint.route("/subs/<int:id>/prune", methods=["GET", "POST"])
def prune_sub(id):
    topic = TopicSubscription.query.filter_by(id=id).first()
    if topic is None:
        return abort(404)
        
    # Raw SQL takes ~1.7 seconds to fetch 500k elements
    mqtt_data = db.session.execute(
        text('''
    SELECT id FROM mqtt WHERE (topic_id=:topic_id);
    '''), {
            'topic_id': topic.id
        }).fetchall()
    # SQLAlchemy takes around ¬22.0 seconds to fetch 500k elements
    # mqtt_data = Mqtt.query.filter_by(topic_id=topic.id).all()

    if topic and topic.deleted:
        if mqtt_data:

            # Remove the data from bulk save scheduler
            timerBulkSave.mqtt_objects = [i for i in timerBulkSave.mqtt_objects if i.topic_id != topic.id]

            # Delete all the associated mqtt data
            start_time = datetime.datetime.now()
            mqtt_data_ids = [item[0] for item in mqtt_data]
            num_records = len(mqtt_data_ids)
            delete_sql = "DELETE FROM mqtt WHERE id IN :ids"

            # SQLITE has limit of variable number limit of 32765 
            for i in range(0, num_records, 32765):
                batch = (
                    mqtt_data_ids[i : i + 32765]
                    if i + 32765 < num_records
                    else mqtt_data_ids[i:]
                )
                query = text(delete_sql).bindparams(
                    bindparam("ids", expanding=True))
                db.session.execute(query, {'ids': batch})
            elapsed_time = datetime.datetime.now() - start_time
            print(elapsed_time)
            
            db.session.commit()

        # remove topic
        db.session.delete(topic)
        db.session.commit()

        flash(f"Topic #{topic.id}:{topic.address} deleted successfully",
              "success")
        return redirect(url_for("main_blueprint.get_all_subs"))
    return redirect(url_for("main_blueprint.get_all_subs"))


@main_blueprint.route("/subs/<int:id>/switch_sub", methods=["GET"])
def switch_subscription_sub(id):
    ts = db.session.query(TopicSubscription).filter_by(id=id).first()
    if ts is None:
        flash(f"Error subscription {id} does not exists!", "error")
        return redirect(url_for("main_blueprint.get_all_subs"))

    ts.subscribe = not ts.subscribe

    with current_app.app_context():
        if ts.subscribe:
            res_mid = mqttc.subscribe(ts.address)
        else:
            res_mid = mqttc.unsubscribe(ts.address)

    if res_mid[0] != mqtt.client.MQTT_ERR_SUCCESS:
        flash(f"Error: {res_mid[0]}", "error")
        return redirect(url_for("main_blueprint.get_all_subs"))
    else:
        flash(f"Address {ts.address} is subscribing: {ts.subscribe}",
              "success")

    db.session.merge(ts)
    db.session.commit()

    update_g_varaible(db)

    return redirect(url_for("main_blueprint.get_all_subs"))


## TOPICS (MQTT Data)


@main_blueprint.route("/topics/")
@main_blueprint.route("/topics/<int:page>")
def get_topics(page=1):
    # Get parameter topic_id and dates
    topic_id = request.args.get("topic_id", None, type=int)
    dt_from = request.args.get("dt_from", None, type=str)
    dt_to = request.args.get("dt_to", None, type=str)
     # Filter by topic_id and dates if provided
    query = Mqtt.query
    if topic_id is not None:
        query = query.filter_by(topic_id=topic_id)
    if dt_from is not None:
        query = query.filter(Mqtt.timestamp >= dt_from)
    if dt_to is not None:
        query = query.filter(Mqtt.timestamp <= dt_to)

    # Order by id in descending order and paginate results
    topics = query.order_by(Mqtt.id.desc()).paginate(
        page=page,
        per_page=current_app.config.get("TOPICS_PER_PAGE") or 50,
        error_out=False)

    # Get all topic subscriptions
    subs = TopicSubscription.query.all()

    return render_template("topics/list.html",
                           topics=topics,
                           subs=subs,
                           title="MQTT Data")


@main_blueprint.route("/topics/delete", methods=["POST"])
def delete_topic():
    topic_ids = request.form.getlist("topic_id")
    deleted_topics = []
    for id in topic_ids:
        topic = Mqtt.query.filter_by(id=id).first()
        if topic:
            db.session.delete(topic)
            db.session.commit()
            deleted_topics.append(topic.id)
        else:
            flash(f"Topic with ID {id} was not found in the database and could not be deleted.", "error")
    if deleted_topics:
        flash(f"The following topics have been deleted: {deleted_topics}", "success")
    return redirect(url_for("main_blueprint.get_topics"))


## Dash


@main_blueprint.route("/dash/")
def get_dash():
    # Get the topics that have 'graph' boolean set to 1
    topics_graph = get_topics_graph(current_app)
    if request.args.get("address") is None and len(topics_graph) >= 1:
        return redirect(
            url_for("main_blueprint.get_dash",
                    address=topics_graph[0].address,
                    id=topics_graph[0].id))

    return render_template("dash/dash.html",
                           title="Visualisation",
                           topics_graph=topics_graph)


@main_blueprint.route("/icons/")
def sensor_icons():
    names_png = get_file_list("icons", ".png")

    ## Get File list
    fileList = []
    for file in os.listdir("./app/static/icons/"):
        if file.endswith(".png"):
            stats = os.stat(os.path.join("./app/static/icons/" + file))
            size = stats.st_size
            date_modified = datetime.datetime.fromtimestamp(
                stats.st_mtime, tz=datetime.timezone.utc)
            date_created = datetime.datetime.fromtimestamp(
                stats.st_ctime, tz=datetime.timezone.utc)

            fileList.append(file)
    return str(fileList)


# socket.io ping test
@main_blueprint.route("/ping")
def ping():
    if notification := NotificationLog.query.order_by(
            NotificationLog.id.desc()).first():
        broadcast_notification_socketio(notification)
        return "ping"
    return "No notification available"


## Lab Dashboard
@main_blueprint.route("/lab")
def lab_dashboard():
    sub_options = get_topic_sub_alerts_with_data_type("json_lab")
    last_data = get_unique_last_json("json_lab")

    return render_template(
        "dash/lab_dashboard.html",
        title="Dashboard",
        sub_options=sub_options,
        last_data=last_data,
    )


# This is used to broadcast randomized json_lab data using socketio (used to test dashboard)
@main_blueprint.route("/lab_ping", methods=["GET", "POST"])
def lab_ping():
    fake_addr = "/fakePods/sensorPodOffice/data"

    spl1 = "/sensorPods/sensorPodLab1/data"
    json_data, timestamp = rand_json_lab_data(spl1, 0, 100, 0, 50, 0, 300,
                                              "1234567891011")

    if (s1 := db.session.query(Mqtt).filter_by(topic=spl1).order_by(
            Mqtt.timestamp.desc()).first()):
        broadcast_json_lab_data(json_data, spl1, timestamp, -1)

    spl2 = "/sensorPods/sensorPodLab2/data"
    json_data, timestamp = rand_json_lab_data(spl2, 0, 100, 0, 50, 0, 300,
                                              "1234567891012")
    broadcast_json_lab_data(json_data, spl2, timestamp, -1)

    spl3 = "/sensorPods/sensorPodLab3/data"
    json_data, timestamp = rand_json_lab_data(spl3, 0, 100, 0, 50, 0, 300,
                                              "1234567891013")
    broadcast_json_lab_data(json_data, spl3, timestamp, -1)

    spo1 = "/sensorPods/sensorPodOffice/data"
    json_data, timestamp = rand_json_lab_data(spo1, 0, 100, 0, 50, 0, 300,
                                              "1234567891014")
    broadcast_json_lab_data(json_data, spl3, timestamp, -1)

    spo2 = "/sensorPods/sensorPodOffice2/data"
    json_data, timestamp = rand_json_lab_data(spo2, 0, 100, 0, 50, 0, 300,
                                              "1234567891015")
    broadcast_json_lab_data(json_data, spl3, timestamp, -1)

    return "PING!"


# Generate random json_lab data
def rand_json_lab_data(address, hum_min, hum_max, temp_min, temp_max,
                       light_min, light_max, msg_id):
    air_hum = str(round(random.uniform(hum_min, hum_max), 2))
    air_temp = str(round(random.uniform(temp_min, temp_max), 2))
    analogue_channels = str(round(random.uniform(light_min, light_max), 0))
    json_data = ('{"moduleName":"' + address + '","messageID":"' + msg_id +
                 '","airHum":' + air_hum + ',"airTemp":' + air_temp +
                 ',"analogueChannelCount":1,"analogueChannels":[' +
                 analogue_channels + "]} ")
    timestamp = str(datetime.datetime.now(datetime.timezone.utc))
    return json_data, timestamp


# JOINs alerts with topic_subscriptions that have data_type #
# TOOD: Change it to SQLAlchemy JOIN statement
def get_topic_sub_alerts_with_data_type(data_type):
    # Get all the subscription that have specific data_type
    subs = get_subs_with_data_type(data_type)

    # Create list of IDs
    topic_ids = [s.id for s in subs]

    # Get alerts associated with topic subscription ids
    alerts = get_alerts(topic_ids)

    # Add alerts to the topic subscription
    sub_dict = []
    for s in subs:
        sub_dict.append(s.to_dict())
        sub_dict[-1]["alerts"] = [
            a.to_dict() for a in alerts if a.topic_id == s.id
        ]
    return sub_dict


# Returns topic subscriptions that have following data_type
def get_subs_with_data_type(data_type):
    return db.session.query(TopicSubscription).filter_by(
        data_type=data_type).all()


# Returns the MQTT json_lab data from last 24 hours
@main_blueprint.route("/get_json_lab_data", methods=["GET", "POST"])
def get_json_lab_data():
    json_lab_subscriptions = (db.session.query(TopicSubscription).filter_by(
        data_type="json_lab").all())

    address_id_list = dict([(j.id, j) for j in json_lab_subscriptions])
    last_24_hr = datetime.datetime.now() - datetime.timedelta(days=1)
    mqtt_json_lab_data = (db.session.query(Mqtt).filter(
        Mqtt.topic_id.in_(address_id_list.keys())).filter(
            Mqtt.timestamp >= last_24_hr).all())

    return jsonify(mqtt_json_lab_data)


@main_blueprint.route("/get_uniq", methods=["GET", "POST"])
def get_uniq():
    js = get_unique_last_json("json_lab")
    return jsonify(js)


# This function returns the alerts associated with the given topic IDs
def get_alerts(topic_ids):
    if isinstance(topic_ids, str):
        topic_ids = list(
            topic_ids.split(",")
        )  # If string: 2,3,4,5 then split it to get the list [2,3,4,5].

    alerts = db.session.query(AlertRule).filter(
        AlertRule.topic_id.in_(topic_ids)).all()
    return alerts


@main_blueprint.route("/get_alerts/<topic_ids>", methods=["GET", "POST"])
def get_alerts_url(topic_ids):
    return get_alerts(topic_ids)


# This function returns the all unique last received MQTT data based on data type.
def get_unique_last_json(data_type):
    # Get all the subscriptions that have the data type
    json_lab_subscriptions = (db.session.query(TopicSubscription).filter_by(
        data_type=data_type).all())

    # Get the IDs from all the subscriptions
    address_id_list = dict([(j.id, j) for j in json_lab_subscriptions])
    al = list(address_id_list.keys())
    # Create the stringified list of IDs separated by commas for SQL query
    addr_keys = ", ".join(map(str, al))

    # Form SQL query to get the MQTT with the following IDs
    q = f"""SELECT * FROM mqtt WHERE id IN 
            (
                SELECT MAX(id)
                FROM mqtt 
                WHERE topic_id IN ({addr_keys})
                GROUP BY topic_id
            );"""

    mqtt_arr = db.session.query(Mqtt).from_statement(text(q)).all()

    # If the data type is JSON_LAB convert value (that is JSON) to python object
    if data_type == "json_lab":
        for idx, x in enumerate(mqtt_arr):
            mqtt_arr[idx].value = json.loads(mqtt_arr[idx].value)

    return mqtt_arr


@main_blueprint.route("/get_json_lab_data/<int:id>", methods=["POST"])
def get_json_lab_data_last_24hr(id=-1):
    data_type = request.form.get("data_type")
    if data_type is None:
        return abort(404)

    hours = int((request.form.get("hours") or 24))

    json_lab_subscription = (db.session.query(TopicSubscription).filter(
        TopicSubscription.data_type == "json_lab").filter(
            TopicSubscription.id == id).first())

    last_24_hr = datetime.datetime.now() - datetime.timedelta(hours=hours)

    if json_lab_subscription:
        mqtt_json_lab_data = (db.session.query(Mqtt).filter(
            Mqtt.topic_id == id).filter(Mqtt.timestamp >= last_24_hr).all())
    else:
        return abort(404)
    return jsonify(mqtt_json_lab_data)


@main_blueprint.route("/get_json_data/<int:id>", methods=["POST"])
def get_json_data(id=-1):
    if request.method == "POST":
        hours = int((request.form.get("hours") or 24))

    json_lab_subscription = (db.session.query(TopicSubscription).filter(
        TopicSubscription.data_type == "json").filter(
            TopicSubscription.id == id).first())

    last_24_hr = datetime.datetime.now() - datetime.timedelta(hours=hours)

    if json_lab_subscription:
        mqtt_json_lab_data = (db.session.query(Mqtt).filter(
            Mqtt.topic_id == id).filter(Mqtt.timestamp >= last_24_hr).all())
    else:
        return abort(404)
    return jsonify(mqtt_json_lab_data)


@main_blueprint.route("/email", methods=["GET", "POST"])
def email_page():
    if request.method == "POST":
        email = request.form.get("email")
        message = request.form.get("message")
        print(email)
        print(message)
        if not email:
            flash("Invalid email address.", "error")
            return render_template("email.html", myemail=myemail)
        if not message:
            flash("Invalid message.", "error")
            return render_template("email.html", myemail=myemail)

        email_message = create_email("Email Test", message, recipients=[email])
        send_email_thread(myemail, email_message, current_app)

        return "POST"
    # send_email_thread(myemail, create_email(
    #     txt, txt, recipients=[alert.email]))
    return render_template("email.html", myemail=myemail)


@main_blueprint.route("/devices", methods=["GET", "POST"])
def get_devices():
    subs = TopicSubscription.query.all()

    return render_template("/subs/devices.html",
                           title="Auto Discover Devices",
                           subs=subs)


@main_blueprint.route("/devices/get", methods=["POST"])
async def get_devices_async():
    new_mqtt_client = mqtt_client.Client()
    if request.method == "POST":
        devices = await get_devices_on_mqtt(new_mqtt_client, 1.0)
        return jsonify(devices)


@main_blueprint.route("/mqtt/send_packet", methods=["POST", "GET"])
async def send_mqtt_message():
    new_mqtt_client = mqtt_client.Client()
    topic = request.args.get("topic")
    message = request.args.get("message")

    print("topic:", topic, "message:", message)
    new_mqtt_client.connect(current_app.config.get('MQTT_URL'), 1883, 60)
    new_mqtt_client.loop_start()
    new_mqtt_client.publish(topic, message)
    new_mqtt_client.loop_stop()

    flash(f"Message '{message}' has been sent to '{topic}'. Please refresh",
          "success")

    return redirect(url_for("main_blueprint.get_devices"))


@main_blueprint.route("/rt/", methods=["GET", "POST"])
def rt_main():
    date_from = request.args.get("date_from") or None
    date_to = request.args.get("date_to") or None
    address = request.args.get("address")
    topic_id = request.args.get("id") or None

    subs = TopicSubscription.query.all()

    return render_template("dash/realtime_graph.html", subs=subs)


async def get_devices_on_mqtt(mqttc: mqtt_client.Client,
                              wait_time: float = 1.0):
    devices = []

    def on_c(c, u, m, r):
        print('on connect')
        print(c, u, m, r)

    def on_m(c, u, m):
        print('on message')
        print(c, u, m)
        val = json.loads(str(m.payload.decode("utf-8")))
        if not devices:
            devices.append(val)

        duplicate = False
        for d in devices:
            if d.get('device_id') == val.get('device_id'):
                duplicate = True
                break
        if not duplicate:
            devices.append(val)

    def on_s(c, u, m, q):
        print('on subscribe')
        print(c, u, m, q)

    mqttc.on_connect = on_c
    mqttc.on_message = on_m
    mqttc.on_subscribe = on_s
    mqttc.connect(current_app.config.get('MQTT_URL'), 1883, 60)
    mqttc.subscribe(current_app.config.get("MQTT_TOPIC_PING_RESPONSE_DEVICES"),
                    2)
    mqttc.loop_start()
    ping_devices_on_mqtt(mqttc)
    await asyncio.sleep(wait_time)
    mqttc.loop_stop()

    return devices


def ping_devices_on_mqtt(mqtt_c: mqtt_client.Client):
    topic_address = "esp32config/PING"
    mqtt_c.publish(topic_address, "")
