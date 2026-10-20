#!/usr/bin/env bash
# Записывает настройки обмена в базу без интерактивного входа (тонкий клиент с /C, нужен графический сеанс).
#   scripts/configure.sh <каталог базы> <адрес маркетплейса> <токен маркетплейса> <ключ API>
set -euo pipefail

IB=$(realpath "${1:?каталог базы}")
URL=${2:?адрес маркетплейса}
MP_TOKEN=${3:?токен маркетплейса}
API_KEY=${4:?ключ API}
V8=${V8:-$(ls -d /opt/1cv8/x86_64/*/ | sort -V | tail -1)}

"$V8/1cv8c" ENTERPRISE /F "$IB" /DisableStartupDialogs /DisableStartupMessages \
  /C "НастроитьОбмен;АдресСервисаМаркетплейса=$URL;ТокенМаркетплейса=$MP_TOKEN;ТокенAPI=$API_KEY"
