#!/bin/bash
# Поднимает quick-туннель Cloudflare и держит PUBLIC_BASE_URL контейнера forma в актуальном виде.
# Идемпотентно: если туннель жив и адрес совпадает — ничего не делает.
# Ставится в cron: @reboot + каждые 5 минут.
set -u

export DOCKER_HOST=tcp://192.168.1.194:2375
export PATH=/home/hermes/bin:/usr/local/bin:/usr/bin:/bin

LOG=/tmp/cloudflared.log
BIN=/home/hermes/bin/cloudflared
TARGET=http://192.168.1.194:8080
SYNC_LOG=/tmp/tunnel-sync.log

# отдельный файл блокировки: старый /tmp/tunnel-up.lock остался открытым
# у запущенного cloudflared (наследовал fd), из-за чего cron молча выходил
exec 9>/home/hermes/workspace/convert/.tunnel.lock
flock -n 9 || exit 0

# 1. туннель жив?
if ! pgrep -f "cloudflared tunnel --url $TARGET" >/dev/null 2>&1; then
  # 9>&- — не отдавать дочернему процессу файл блокировки, иначе он держит его вечно
  nohup "$BIN" tunnel --url "$TARGET" --no-autoupdate > "$LOG" 2>&1 9>&- &
  sleep 14
fi

# 2. адрес из лога
URL=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$LOG" 2>/dev/null \
      | grep -v '^https://api\.' | tail -1)
[ -z "${URL:-}" ] && exit 0

# 2b. всегда держим актуальный адрес в удобном файле
echo "$URL" > /home/hermes/forma-url.txt

# 3. что сейчас в контейнере
CUR=$(docker inspect forma --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null \
      | sed -n 's/^PUBLIC_BASE_URL=//p' | head -1)
[ "$CUR" = "$URL" ] && exit 0

# 4. адрес сменился — пересоздаём контейнер
docker rm -f forma >/dev/null 2>&1
docker run -d --name forma --restart unless-stopped -p 8080:8080 \
  -e PUBLIC_BASE_URL="$URL" -e TTL_DAYS=7 -e MAX_UPLOAD_MB=100 \
  --shm-size=512m -v forma_data:/data forma:latest >/dev/null
echo "$(date -Is) PUBLIC_BASE_URL -> $URL" >> "$SYNC_LOG"
