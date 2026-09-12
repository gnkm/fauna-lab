# FaunaLab の OCI 定義（正本）。Podman / Docker の双方で `build` できること。
# Dockerfile は同一内容の Docker 向け別名である。
#
# セットアップ段階（ネットワーク可）でベースイメージと依存を取得する。
# 実行段階では外部レジストリへ取りに行かない（compose の pull_policy: never）。
#
# マルチステージ: フロントを pnpm build し、実行イメージは Python ランタイムと
# 静的ファイルとロック済み Python 依存だけにする。ベースライン重みはイメージに
# コピーしない（実行時に assets/ を読み取り専用マウント）。

# --- フロント（Vite） -------------------------------------------------------
FROM node:22-bookworm-slim AS web

WORKDIR /src
ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY web/package.json web/
RUN corepack enable && corepack prepare pnpm@10.33.3 --activate \
    && pnpm install --frozen-lockfile

COPY web/ web/
RUN pnpm --filter web build

# --- Python 依存（パスを実行ステージと揃えて venv の shebang を保つ） ----------
FROM python:3.12-slim-bookworm AS python-builder

COPY --from=ghcr.io/astral-sh/uv:0.12.13 /uv /usr/local/bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

COPY backend/pyproject.toml backend/uv.lock backend/
COPY backend/faunalab /app/backend/faunalab
RUN uv sync --directory backend --frozen --no-dev

# --- 実行 -------------------------------------------------------------------
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/backend/.venv/bin:$PATH" \
    PYTHONPATH="/app/backend"

WORKDIR /app

COPY --from=python-builder /app/backend/.venv /app/backend/.venv
COPY --from=python-builder /app/backend/faunalab /app/backend/faunalab
COPY --from=web /src/web/dist /app/web/dist
COPY container/entrypoint.sh /entrypoint.sh

RUN chmod 0755 /entrypoint.sh

EXPOSE 8000

# ルートレスでは uid 0 のまま（ホストユーザーに写る）。rootful のみ entrypoint が
# FAUNALAB_UID へ落とす。bind を無条件に 1000 へ chown しない（DESIGN I-UID-001）。
ENTRYPOINT ["/entrypoint.sh"]

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/', timeout=2)"

CMD ["uvicorn", "faunalab.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
