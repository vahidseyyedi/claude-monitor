#!/usr/bin/env bash
# نصب آیکون دسکتاپ برای «کلاد مانیتور».
# این اسکریپت رو یه‌بار اجرا کن: bash install.sh
# بعدش یه آیکون به اسم «کلاد مانیتور» روی دسکتاپ و/یا توی منوی برنامه‌ها پیدا می‌کنی.
# با زدنش، سرور (اگه روشن نباشه) بی‌صدا و بدون باز شدن ترمینال روشن میشه
# و صفحه‌ی داشبورد توی مرورگر پیش‌فرضت باز میشه.
#
# ساخته‌شده برای لینوکس (GNOME/KDE و هر محیطی که از فایل .desktop پشتیبانی کنه).

set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVER_DIR="$DIR/server"
ICON="$DIR/assets/claude-monitor.png"
LAUNCH="$DIR/claude-monitor-launch.sh"
PORT=8765

if [ ! -f "$ICON" ]; then
  echo "هشدار: آیکون پیدا نشد ($ICON) — بدون آیکون ادامه میدم." >&2
fi

# ---------- اسکریپت لانچر: سرور رو (اگه روشن نیست) بی‌صدا بالا میاره و مرورگر رو باز می‌کنه ----------
cat > "$LAUNCH" <<EOF
#!/usr/bin/env bash
# اگه سرور از قبل روی این پورت روشنه، دوباره اجراش نکن
if ! curl -s -o /dev/null "http://localhost:$PORT/"; then
  cd "$SERVER_DIR"
  nohup python3 server.py >> /tmp/claude-monitor.log 2>&1 &
  disown
  # کمی صبر کن تا سرور بالا بیاد
  for i in 1 2 3 4 5 6 7 8 9 10; do
    curl -s -o /dev/null "http://localhost:$PORT/" && break
    sleep 0.5
  done
fi

xdg-open "http://localhost:$PORT/" >/dev/null 2>&1 \\
  || gio open "http://localhost:$PORT/" >/dev/null 2>&1 \\
  || sensible-browser "http://localhost:$PORT/" >/dev/null 2>&1 \\
  || echo "نتونستم مرورگر رو خودکار باز کنم؛ خودت برو به http://localhost:$PORT/"
EOF
chmod +x "$LAUNCH"

# ---------- فایل .desktop برای منوی برنامه‌ها ----------
APPS_DIR="$HOME/.local/share/applications"
mkdir -p "$APPS_DIR"
DESKTOP_FILE="$APPS_DIR/claude-monitor.desktop"

cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=Claude Monitor
Comment=Claude Monitor
Exec=$LAUNCH
Icon=$ICON
Terminal=false
Categories=Utility;
EOF
chmod +x "$DESKTOP_FILE"

# ---------- یه کپی هم مستقیم روی دسکتاپ (اگه پوشه‌ی Desktop وجود داشته باشه) ----------
for DESK in "$HOME/Desktop" "$HOME/میزکار"; do
  if [ -d "$DESK" ]; then
    cp "$DESKTOP_FILE" "$DESK/claude-monitor.desktop"
    chmod +x "$DESK/claude-monitor.desktop"
    # توی گنوم/نوتیلوس تا این "trusted" نشه، هر بار قبل از اجرا یه هشدار میده
    command -v gio >/dev/null 2>&1 && gio set "$DESK/claude-monitor.desktop" metadata::trusted true >/dev/null 2>&1 || true
  fi
done

update-desktop-database "$APPS_DIR" >/dev/null 2>&1 || true

echo "نصب شد."
echo "آیکون «کلاد مانیتور» رو روی دسکتاپ یا توی منوی برنامه‌ها پیدا کن و باهاش اجرا کن."
echo "(لاگ سرور موقع اجرا با آیکون، توی /tmp/claude-monitor.log نوشته میشه.)"
