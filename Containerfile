# FaunaLab の OCI 定義（正本）。Podman / Docker の双方で `build` できること。
# Dockerfile は同一内容の Docker 向け別名である。
#
# セットアップ段階（ネットワーク可）でベースイメージと依存を取得する。
# 実行段階では外部レジストリへ取りに行かない（compose の pull_policy: never）。
#
# アプリ本体（FastAPI / 静的 UI）は後続 Issue。本イメージは待受ポート 8000 と
# マウント契約を固定するためのプレースホルダである。フロントは骨格 Issue で
# `pnpm build` し、Python 依存は `uv.lock` 導入後に実行ステージへ焼き込む。
# ベースライン重みはイメージにコピーしない（実行時に assets/ を読み取り専用マウント）。

FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY container/www/index.html /app/index.html
COPY container/entrypoint.sh /entrypoint.sh

RUN chmod 0755 /entrypoint.sh

EXPOSE 8000

# ルートで起動し、entrypoint がデータディレクトリを FAUNALAB_UID（既定 1000）へ
# chown してからその UID へ落とす。nobody 固定だとホストの ./data に書けない。
ENTRYPOINT ["/entrypoint.sh"]

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/', timeout=2)"

CMD ["python", "-m", "http.server", "8000", "--bind", "0.0.0.0"]
