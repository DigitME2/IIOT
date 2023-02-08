# MQTT Client with Flask and Dash
 Flask IIOT software that is used to collect the data from sensors using MQTT.
 
# Installation

### Automaticially (Linux Only)
Install automatically by runing the setup.sh script
```bash
# Linux Only
source setup.sh
```

### Manually 
Create virtual env:
```bash
# On Linux
sudo apt-get install python3.9-venv
python3.9 -m venv venv
source venv/bin/activate

# On Windows
python -m venv venv
```
Activate virtual env:

```bash
# On Windows
venv\Scripts\activate

# On Linux
source venv/bin/Activate
```

Install required libraries by using python pip:
```bash
# On Windows
pip install -r requirements.txt

# On Linux
pip3 install -r requirements.txt
```

Install Mosquitto or other MQTT broker
```bash
# On Windows
# Download and install Mosquitto from official Mosquitto website
https://mosquitto.org/download/

# Run mosquitto with the mosquitto.conf configuration
C:\Program Files\mosquitto\mosquitto.exe -c mosquitto.conf


# On Linux
sudo apt install -y mosquitto

# Confirm the status of the Mosquitto service
sudo systemctl start mosquitto
sudo systemctl status mosquitto

# Copy the mosuqitto.conf to /etc/mosquitto/mosquitto.conf
sudo cp mosquitto.conf /etc/mosquitto/conf.d

# Restart the service
sudo systemctl restart mosquitto
```

# How to run
```bash 
# On Linux
python3.9 run.py
Running on http://localhost:5000/ (Press CTRL+C to quit)

# On Windows
python run.py
Running on http://localhost:5000/ (Press CTRL+C to quit)
```



How to run as a service on Linux.
```bash
# Create a file named iiot_server.service
$ nano iiot_server.service 
# Paste the following:
[Unit]
Description=IIOT server
After=network.target

[Service]
User=user
WorkingDirectory=/home/user/iot
ExecStart=/home/user/iot/venv/bin/python3 /home/user/iot/run_ubuntu.py
Restart=always

[Install]
WantedBy=multi-user.target

# Move iiot_server.service file to /etc/systemd/system 
$ mv iiot_server.service /etc/systemd/system

# Reload deamon: 
$ sudo systemctl daemon-reload
# Enable service to start on boot
$ sudo systemctl enable iiot_server
# Start the service now
$ sudo systemctl start iiot_server
```


