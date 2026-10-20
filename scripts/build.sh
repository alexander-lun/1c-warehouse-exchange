#!/usr/bin/env bash
# Сборка файловой информационной базы из исходников.
#   scripts/build.sh [каталог базы]            по умолчанию build/ib
#   V8=/opt/1cv8/x86_64/<версия> scripts/build.sh   другая версия платформы
set -euo pipefail
IB=$(realpath -m "${1:-$(dirname "$0")/../build/ib}")
cd "$(dirname "$0")/.."
V8=${V8:-$(ls -d /opt/1cv8/x86_64/*/ | sort -V | tail -1)}

if [[ ! -f $IB/1Cv8.1CD ]]; then
  "$V8/ibcmd" infobase create --db-path="$IB"
fi
"$V8/ibcmd" infobase config import --db-path="$IB" src
"$V8/ibcmd" infobase config apply --db-path="$IB" --force

# Проверка модулей (нужна лицензия на клиентскую часть)
LOG=$(mktemp)
if ! "$V8/1cv8" DESIGNER /F "$IB" /DisableStartupDialogs /DisableStartupMessages \
     /CheckModules -ThinClient -Server /Out "$LOG"; then
  cat "$LOG"; rm -f "$LOG"; exit 1
fi
rm -f "$LOG"
echo "База собрана: $IB"
