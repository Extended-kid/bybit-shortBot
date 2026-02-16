#!/bin/bash

echo "Deploying Bybit Short Bot..."

mkdir -p /home/user/bybit-bot/data
mkdir -p /home/user/bybit-bot/data/logs

rsync -av --exclude 'data' --exclude 'venv' --exclude '.git' \
    ./ /home/user/bybit-bot/

cd /home/user/bybit-bot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

sudo tee /etc/systemd/system/bybit-bot.service > /dev/null <<EOF
[Unit]
Description=Bybit Short Trading Bot
After=network.target

[Service]
Type=simple
User=user
WorkingDirectory=/home/user/bybit-bot
Environment=PYTHONUNBUFFERED=1
ExecStart=/home/user/bybit-bot/venv/bin/python /home/user/bybit-bot/bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable bybit-bot
sudo systemctl restart bybit-bot

echo "Deploy complete!"
