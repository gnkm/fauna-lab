# Fauna Lab

![CI](https://github.com/gnkm/fauna-lab/actions/workflows/ci.yml/badge.svg)

犬種分類システム。
[SRS](docs/source-of-truth/srs-faunalab.md)の内容を実装する。
成果物は、[タスク書類](docs/source-of-truth/task-faunalab.md)に記載の内容。

実装前の技術選定・実行形態・データ配置は [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) を正とする。提出物の `DESIGN.md` とは別物である。

## 起動（Podman）

実行環境は **Podman** です（REQ-CON-002）。対象は Linux（x86_64 / arm64）と macOS です。Windows は任意です。

セットアップ（イメージ build・依存取得）と実行は分けます。起動以降は外部ネットワーク接続が無い前提で動きます。

### 前提

- **Linux**: Podman 4 以降と Compose プロバイダ（`podman compose` が使えること）
- **macOS**: Podman Desktop、または `podman machine init` / `podman machine start` のあと、同じコマンドを Machine 上で実行する
- 開発時の静的解析・試験: Python 3.12、[uv](https://docs.astral.sh/uv/)、Node.js 22、pnpm 10
- 既定の待受はホストのポート **8000**。変更は環境変数 `FAUNALAB_PORT`（コンテナ内の待受は常に 8000）

### セットアップ（ネットワークを利用してよい）

リポジトリ直下で:

```bash
podman compose build
```

### 実行（起動後は外部ネットワーク不要）

リポジトリ直下の単一コマンド:

```bash
podman compose up --pull never
```

ブラウザで `http://127.0.0.1:8000/` を開く。`--build` は実行コマンドに含めない（セットアップと実行を混ぜない）。

- 配布資産 `assets/` は読み取り専用でマウントする。無くても起動する。
- 実行時データは `${FAUNALAB_DATA_DIR:-./data}` にだけ書く。ルートレス Podman ではコンテナ内 uid 0 がホストユーザーに写る。rootful（Cloud の Docker など）では `FAUNALAB_UID`（既定 1000）で書き、ホストユーザーが `./data` を管理できるようにする。

詳細（環境変数、マウント先、ネットワーク分離）は [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) 5–6 節。

### Cursor Cloud Agent

同一の `compose.yaml` と `Containerfile` を **Docker** で起動する。差分はコマンド名だけである。

```bash
docker compose build
docker compose up --pull never
```

## 試験と静的解析

クローン後、開発依存を入れてから次の単一コマンドを使う（外部ネットワーク不要）。

```bash
pnpm install
uv sync --directory backend --frozen
```

| 目的 | コマンド |
| --- | --- |
| 試験（単一） | `pnpm test` |
| 静的解析（単一） | `pnpm lint` |

`pnpm test` は `uv run --directory backend pytest` である。カバレッジは計測するが、70 % 未満で落とす enforce は F018/F019（未実装コードで落とさないため）。

`pnpm lint` は Biome（フロント）と Ruff / Pyright（バックエンド）をまとめて実行する。

ライセンス一覧の再生成（セットアップ段階、ネットワーク可）:

```bash
pnpm export-licenses
```

生成物は `docs/dependency-licenses-python.md` と `docs/dependency-licenses-web.txt`（`scripts/export_licenses.py`）。実行段階ではライセンス取得のためにネットへ出ない。

サンプルデータの投入手順は、画像登録 API が揃ったあとの Issue で README に足す。

## コントリビューション

ブランチ命名とコミット規約は [CONTRIBUTING.md](CONTRIBUTING.md) を参照してください。
