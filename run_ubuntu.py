from app import init_app, socketio

app = init_app()

if __name__ == "__main__":
    # debug=False otherwise websocket won't work from the MQTT layer
    socketio.run(app, host='127.0.0.1', port=5050, debug=False, allow_unsafe_werkzeug=True)
