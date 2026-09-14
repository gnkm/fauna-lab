# Fauna Lab

![CI](https://github.com/gnkm/fauna-lab/actions/workflows/ci.yml/badge.svg)

犬種分類システム。
[SRS](docs/source-of-truth/srs-faunalab.md)の内容を実装する。
成果物は、[タスク書類](docs/source-of-truth/task-faunalab.md)に記載の内容。

提出物の設計は [DESIGN.md](DESIGN.md)。HTTP API の契約は [openapi.yaml](openapi.yaml)（OpenAPI 3.1、実装と一致）。言語・実行形態・データ配置の実装前合意は [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)。

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
| UI 受入（Playwright） | `pnpm test:e2e`（先に `pnpm --filter web build`。ブラウザは `pnpm exec playwright install chromium`。システムの Google Chrome を使う場合は `PW_CHANNEL=chrome`） |
| 静的解析（単一） | `pnpm lint` |

`pnpm test` は `uv run --directory backend pytest` である。行カバレッジ 70 % 未満で失敗する（REQ-ATT-MNT-001）。SRS 4 章の VER ID から試験へは [docs/verification-matrix.md](docs/verification-matrix.md) または `pytest -m ver_obs_001` で辿る。

`pnpm lint` は Biome（フロント）と Ruff / Pyright（バックエンド）をまとめて実行する。

ライセンス一覧の再生成（セットアップ段階、ネットワーク可）:

```bash
pnpm export-licenses
```

生成物は `docs/dependency-licenses-python.md` と `docs/dependency-licenses-web.txt`（`scripts/export_licenses.py`）。実行段階ではライセンス取得のためにネットへ出ない。

### サンプル投入

配布資産 `assets/sample/manifest.json` があるとき、確定ラベル（由来 `human`）付きで登録できます。Web UI の概況画面にある「サンプルデータを投入」から実行できます。API から行う場合:

```bash
curl -sS -X POST http://127.0.0.1:8000/api/sample/import
curl -sS http://127.0.0.1:8000/api/_state
```

`assets/sample/` が無い、またはマニフェスト／画像が読めない場合は HTTP 422（`sample_unavailable`）で失敗します。起動自体は継続します（REQ-F-SYS-003）。

観測 `GET /api/_state` は読み取り専用です。評価と受入確認はここを見ます。

画像の登録・ラベル・分割・学習・推論は Web UI からも行えます。

- 画像: `http://127.0.0.1:8000/images`（複数 JPEG/PNG、一部失敗は件別に表示）
- アノテーション: `http://127.0.0.1:8000/annotate`（1 枚付与、一括付与、候補の生成・採用・却下・閾値一括採用。並びの既定は信頼度昇順）
- 分割: `http://127.0.0.1:8000/splits`（比率とシード、件数の表示）
- 学習: `http://127.0.0.1:8000/train`（既定パラメータで開始、進捗の自動更新、中止は確認ダイアログ）
- モデル: `http://127.0.0.1:8000/models`（版 0 は内蔵表示。有効化・再評価。有効モデルと版 0 は削除しない）
- 推論: `http://127.0.0.1:8000/infer`（新規ファイルと登録済。有効モデルが無いときはその旨を表示）

確定ラベルの付与・一括付与・層化分割・件数概況を API で行う場合:

```bash
curl -sS -X PUT http://127.0.0.1:8000/api/images/<ref>/label \
  -H 'content-type: application/json' \
  -d '{"class_id":"samoyed","source":"human"}'
curl -sS -X POST http://127.0.0.1:8000/api/labels/bulk \
  -H 'content-type: application/json' \
  -d '{"refs":["<ref>"],"class_id":"boxer"}'
curl -sS -X POST http://127.0.0.1:8000/api/splits -H 'content-type: application/json' -d '{}'
curl -sS http://127.0.0.1:8000/api/stats
```

## 主要な設計判断

REQ-ATT-MNT-004。根拠と不採用案の詳細は [DESIGN.md](DESIGN.md)。

| 判断 | 根拠 |
| --- | --- |
| 実行は **Podman Compose**。単一コマンドは `podman compose up --pull never`。セットアップは `podman compose build` | 提出時の単一起動（REQ-CON-002）。実行段階でレジストリへ取りに行かない。Cloud Agent だけ `docker compose` に読み替える（I-ENV-001） |
| コンテナは `app` 1 つ。学習は同一コンテナの別プロセス | SQLite とデータディレクトリ複製を単純に保つ。API を学習でブロックしない |
| 状態は SQLite（WAL）とデータディレクトリ上のファイル | 停止後にディレクトリ全体を複製すれば復元できる（REQ-ATT-POR-001） |
| API プロセスは ONNX Runtime のみ。学習は NumPy でヘッド／小型 CNN を訓練し ONNX を書く | 常駐メモリ（REQ-PERF-006）。PyPI の `torch` 車輪は CUDA 再配布を含みライセンス方針と衝突する（I-TRN-003） |
| 誤りは RFC 9457。REQ-API-003 の 7 状況は異なる HTTP ステータス | 409 は対象の状態衝突、422 はシステム前提の不足（I-ERR-001） |
| `GET /api/_state` は内部表を SRS 語彙へ変換するだけ | 評価窓であり、永続スキーマをそのまま返さない |

## コントリビューション

ブランチ命名とコミット規約は [CONTRIBUTING.md](CONTRIBUTING.md) を参照してください。
