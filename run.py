from app import init_app, socketio

app = init_app()

if __name__ == "__main__":
    # debug=False otherwise websocket won't work from the MQTT layer
    socketio.run(app, host='0.0.0.0', port=80, debug=False)