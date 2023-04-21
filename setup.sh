echo =================
echo Generate services file
echo =================

> iiot_server.service
echo [Unit] >> iiot_server.service
echo Description=IIOT server >> iiot_server.service
echo After=network.target >> iiot_server.service
echo >> iiot_server.service
echo [Service] >> iiot_server.service
echo User="$USER" >> iiot_server.service
echo WorkingDirectory="$PWD" >> iiot_server.service
echo ExecStart="$PWD"/venv/bin/python3.11  "$PWD"/run_ubuntu.py >> iiot_server.service
echo Restart=always >> iiot_server.service
echo >> iiot_server.service
echo [Install] >> iiot_server.service
echo WantedBy=multi-user.target >> iiot_server.service

echo Finished generating services file
echo ""

echo =================
echo Move file to /etc/systemd/system
echo =================

sudo mv iiot_server.service /etc/systemd/system

echo ""
echo =================
echo Install virtualenv
echo =================

sudo add-apt-repository -y ppa:deadsnakes/ppa 
sudo apt-get -y install python3.11

virtualenv -p python3.11 venv

echo =================
echo Activate virtualenv
echo =================

source venv/bin/activate

echo =================
echo Install pip
echo =================

sudo apt-get -y install python3-distutils
sudo apt-get -y install python3-apt

echo =================
echo Install pip packages
echo =================

python3.11 -m pip install -r requirements.txt

echo =================
echo Update the packages list 
echo =================

sudo apt update

echo =================
echo Install mosquitto
echo =================

sudo apt-get -y install mosquitto

echo =================
echo Copy the mosquitto.conf file
echo =================

sudo cp mosquitto.conf /etc/mosquitto/conf.d

echo =================
echo Restart mosquitto
echo =================

sudo systemctl stop mosquitto
sudo systemctl start mosquitto

echo =================
echo Reload daemon
echo =================

sudo systemctl daemon-reload

echo =================
echo Start the IIOT server
echo =================

sudo systemctl enable iiot_server
sudo systemctl start iiot_server
sudo systemctl | grep iiot_server
