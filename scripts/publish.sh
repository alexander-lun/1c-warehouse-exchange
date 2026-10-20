#!/usr/bin/env bash
# Публикация базы на локальном Apache, запущенном от текущего пользователя (без root).
#   scripts/publish.sh <каталог базы> [имя публикации] [порт]   → http://127.0.0.1:<порт>/<имя>/hs/api/...
#   scripts/publish.sh --stop
set -euo pipefail
cd "$(dirname "$0")/.."
WEB=$PWD/build/web

if [[ ${1:-} == --stop ]]; then
  [[ -f $WEB/httpd.pid ]] && kill "$(cat "$WEB/httpd.pid")" && echo "Apache остановлен"
  rm -f "$WEB/httpd.pid"
  exit 0
fi

IB=$(realpath "${1:?каталог базы}")
NAME=${2:-warehouse}
PORT=${3:-8081}
V8=${V8:-$(ls -d /opt/1cv8/x86_64/*/ | sort -V | tail -1)}
MODULES=${APACHE_MODULES:-/usr/lib64/httpd/modules}

mkdir -p "$WEB/$NAME" "$WEB/logs"

cat > "$WEB/$NAME/default.vrd" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<point xmlns="http://v8.1c.ru/8.2/virtual-resource-system"
       xmlns:xs="http://www.w3.org/2001/XMLSchema"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       base="/$NAME" ib="File=&quot;$IB&quot;;">
  <httpServices publishByDefault="true" publishExtensionsByDefault="true"/>
</point>
EOF

cat > "$WEB/httpd.conf" <<EOF
ServerRoot "/etc/httpd"
ServerName localhost
PidFile "$WEB/httpd.pid"
Listen 127.0.0.1:$PORT
LoadModule mpm_prefork_module $MODULES/mod_mpm_prefork.so
LoadModule unixd_module       $MODULES/mod_unixd.so
LoadModule authz_core_module  $MODULES/mod_authz_core.so
LoadModule log_config_module  $MODULES/mod_log_config.so
LoadModule _1cws_module       "$V8/wsap24.so"
ErrorLog  "$WEB/logs/error.log"
LogFormat "%h %t \"%r\" %>s %b %D" short
CustomLog "$WEB/logs/access.log" short
DocumentRoot "$WEB"
<Directory "$WEB">
  AllowOverride None
  Require all granted
</Directory>
<Location "/$NAME">
  SetHandler 1c-application
  ManagedApplicationDescriptor "$WEB/$NAME/default.vrd"
</Location>
EOF

if [[ -f $WEB/httpd.pid ]] && kill "$(cat "$WEB/httpd.pid")" 2>/dev/null; then
  for _ in {1..20}; do ss -ltn | grep -q ":$PORT " || break; sleep 0.5; done
fi
/usr/sbin/httpd -f "$WEB/httpd.conf" -k start
echo "http://127.0.0.1:$PORT/$NAME/hs/api/"
