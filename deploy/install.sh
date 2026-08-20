#!/usr/bin/env bash
set -e

echo "=== ShortsGo: установка на VPS (Ubuntu/Debian) ==="
echo "Файлы бота берутся из GitHub-репозитория: https://github.com/AcegnoK/youtube-shorts-bot"

APP_DIR=/opt/shortsbot
GIT_URL=https://github.com/AcegnoK/youtube-shorts-bot.git
BRANCH=master

sudo apt update
sudo apt install -y python3 python3-venv git

sudo mkdir -p $APP_DIR
sudo chown "$USER" $APP_DIR

if [ ! -d "$APP_DIR/.git" ]; then
    git clone -b $BRANCH $GIT_URL $APP_DIR
else
    git -C $APP_DIR pull origin $BRANCH
fi

cd $APP_DIR

python3 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt

echo ""
echo "=== ПЕРЕНЕСИТЕ СЕКРЕТЫ НА СЕРВЕР ==="
echo "Положите сюда (в $APP_DIR):"
echo "  .env              - токен бота, ключи Upload-Post/TikTok/Instagram"
echo "  client_secret.json - ключи Google для YouTube"
echo "  token.pickle      - токен авторизации YouTube (или авторизуйтесь заново через бота)"
echo "Рекомендуется скопировать с Windows-компьютера (закрыв бота там)."
echo "Пример: scp .env client_secret.json token.pickle root@IP:$APP_DIR/"
read -r -p "Готово? Нажмите Enter, чтобы запустить сервис..." _

sudo cp deploy/shortsbot.service /etc/systemd/system/shortsbot.service
sudo systemctl daemon-reload
sudo systemctl enable shortsbot
sudo systemctl restart shortsbot

echo ""
echo "=== ГОТОВО ==="
echo "Состояние: sudo systemctl status shortsbot"
echo "Логи:      sudo journalctl -u shortsbot -f"