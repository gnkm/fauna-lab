# Fauna Lab

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
- 実行時データは `${FAUNALAB_DATA_DIR:-./data}` にだけ書く。起動時にディレクトリ所有者を UID 1000（`FAUNALAB_UID` / `FAUNALAB_GID`）へ揃える。

詳細（環境変数、マウント先、ネットワーク分離）は [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) 5–6 節。

### Cursor Cloud Agent

同一の `compose.yaml` と `Containerfile` を **Docker** で起動する。差分はコマンド名だけである。

```bash
docker compose build
docker compose up --pull never
```

## コントリビューション

ブランチ命名とコミット規約は [CONTRIBUTING.md](CONTRIBUTING.md) を参照してください。
