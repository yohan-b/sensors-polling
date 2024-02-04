#!/bin/bash
#Absolute path to this script
SCRIPT=$(readlink -f $0)
#Absolute path this script is in
SCRIPTPATH=$(dirname $SCRIPT)
SERVICE="sensors-polling"

cat << EOF > /etc/systemd/system/${SERVICE}.service
[Unit]
Description=Starting ${SERVICE}
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
ExecStart=$SCRIPTPATH/${SERVICE}.py
WorkingDirectory=$SCRIPTPATH

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable ${SERVICE}.service

