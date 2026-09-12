#!/bin/sh
# データ bind の所有者を実行 UID に揃え、その UID へ落ちてから CMD を実行する。
# プレースホルダはルートで起動し、nobody 固定だとホストの ./data に書けないため。
set -e
data="${FAUNALAB_DATA_DIR:-/var/lib/faunalab}"
uid="${FAUNALAB_UID:-1000}"
gid="${FAUNALAB_GID:-1000}"
mkdir -p "$data"
if [ "$(id -u)" = "0" ]; then
  chown -R "${uid}:${gid}" "$data"
  exec setpriv --reuid="$uid" --regid="$gid" --clear-groups -- "$@"
fi
exec "$@"
