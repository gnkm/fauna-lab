#!/bin/sh
# データ bind の所有権は user namespace で分岐する（DESIGN I-UID-001）。
# ルートレス: コンテナ uid 0 はホストユーザー。chown しない。
# rootful: ホストの通常ユーザーが管理できるよう FAUNALAB_UID へ落とし、必要なら chown する。
set -e
data="${FAUNALAB_DATA_DIR:-/var/lib/faunalab}"
mkdir -p "$data"

if [ "$(id -u)" = "0" ]; then
  read -r cstart hstart _count <<EOF
$(awk 'NR==1 {print $1, $2, $3}' /proc/self/uid_map)
EOF
  if [ "$cstart" = "0" ] && [ "$hstart" = "0" ]; then
    uid="${FAUNALAB_UID:-1000}"
    gid="${FAUNALAB_GID:-1000}"
    chown -R "${uid}:${gid}" "$data"
    exec setpriv --reuid="$uid" --regid="$gid" --clear-groups -- "$@"
  fi
fi

exec "$@"
