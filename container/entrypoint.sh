#!/bin/sh
# データ bind の所有権は user namespace で分岐する（DESIGN I-UID-001）。
# ルートレス: コンテナ uid 0 はホストユーザー。chown しない。
# rootful: ホストの通常ユーザーが管理できるよう FAUNALAB_UID へ落とし、必要なら chown する。
# 権限降下は Python（stdlib）。slim イメージに setpriv が無い場合がある。
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
    case "$uid" in *[!0-9]*) echo "invalid FAUNALAB_UID: $uid" >&2; exit 1 ;; esac
    case "$gid" in *[!0-9]*) echo "invalid FAUNALAB_GID: $gid" >&2; exit 1 ;; esac
    chown -R "${uid}:${gid}" "$data"
    export FAUNALAB_DROP_UID="$uid"
    export FAUNALAB_DROP_GID="$gid"
    exec python -c 'import os, sys
os.setgid(int(os.environ["FAUNALAB_DROP_GID"]))
os.setuid(int(os.environ["FAUNALAB_DROP_UID"]))
os.execvp(sys.argv[1], sys.argv[1:])
' "$@"
  fi
fi

exec "$@"
