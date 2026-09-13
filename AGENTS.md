# AGENTS.md

Cursor Cloud Agents 向けの作業ルール。アプリ固有のルールはプロジェクト側で追記する。

## 編集禁止（読み取り専用）

- `docs/source-of-truth/` 配下はソース・オブ・トゥルース。AI は読んでよいが、編集・削除・リネーム・移動は禁止。
- `assets/` 配下は配布資産。AI は読んでよいが、生成・改変・削除・リネーム・移動は禁止。
- フロントマターに `ai.editable: false`（または `ai_editable: false`）があるファイルも同様。
- 内容変更が必要なら Issue で人間に依頼し、自分では触らない。

## タスク管理

- タスクと完了基準は **GitHub Issue** のみ。着手前に対象 Issue を読む（`gh issue view`）。
- Issue の **Blocked by** に未完了の依存がある場合は着手しない。
- セッション引き継ぎは Issue / PR の本文とコメントで行う。リポジトリ内の progress ファイルは使わない。

## 完了の定義

- Issue のクローズは、`verifier` が Issue の **検証** 欄のコマンドを実行して通ったあとだけ。
- 自分で完了と主張した直後は `verifier` を起動する。

## 調査

- ウェブ調査は親が直接 scrape / WebFetch / Firecrawl せず、`web-reader` に委譲する。

## CI バッジ

- CI ワークフロー（`.github/workflows/`）を追加・変更したら、README 先頭付近にそのワークフローの状況バッジを必ず出す。無ければ追加する。
- 例: `![CI](https://github.com/<owner>/<repo>/actions/workflows/<file>.yml/badge.svg)`

## Cursor Cloud specific instructions

### Environment

- 技術スタックと実行形態は `docs/ARCHITECTURE.md` を正とする。
  - バックエンド: Python 3.12 / FastAPI / SQLite / uv
  - フロント: TypeScript / Vite / React / pnpm
  - 実行: ローカルと提出は **Podman**。Cursor Cloud Agent では同一の OCI 定義（`compose.yaml` と `Containerfile` / リポジトリ直下の `Dockerfile`）を **Docker** で動かす。差分はコマンド名だけ。アプリ用の Cloud 専用イメージ定義は作らない。
- Cloud VM 自体は `.cursor/Dockerfile`（Python 3.12 / Node 22 / Docker CE）。アプリの `Containerfile` とは役割を分ける。`.cursor/environment.json` がこれを `build.dockerfile` から参照する。
- `install`（セットアップ、ネット可、冪等）: `pnpm install --frozen-lockfile` と `uv sync --directory backend --frozen`（CI / Containerfile と同じ固定）、続けて `docker compose build`。デーモン起動を待ってから build する。
- `start`: `sudo service docker start` のみ。アプリ本体は置かない。
- `terminals`: `docker compose up --pull never`（提出の `podman compose up --pull never` に相当）。
- `ports`: **8000**（コンテナ内待受。ホスト公開の既定も 8000）。
- 長時間常駐プロセスは `install` に置かない。
- 実行時オフラインはアプリの責務（REQ-CON-001）。Cloud VM の egress を完全遮断しない（Cursor / SCM 必須ドメインが残る）。

### 起動と試験（Cloud）

`install` 済みなら依存とアプリイメージは揃っている。追加のセットアップと実行:

```bash
docker compose build
docker compose up --pull never
```

試験・静的解析（ホスト上。外部ネットワーク不要）:

```bash
pnpm test
pnpm lint
```

ローカル / 提出では `podman compose` に読み替える。

### 検証

- 変更後は可能な範囲で自動試験・型検査・リンタを回してから PR にする。
- CI ワークフロー追加後は、PR 上の Checks を確認する。
- Issue の **検証** 欄がある場合は、そのコマンドを満たすこと。クローズ前に `verifier` を起動する。

### 秘密情報

- シークレットをコミットしない。Cursor Secrets または GitHub Actions secrets を使う。
- `.env` はリポジトリに含めない。

### このリポジトリの制約

- 実行時の外部ネットワーク接続禁止など、仕様上の制約は `docs/source-of-truth/` を参照（編集はしない）。
- `.cursor/hooks.json` により `docs/source-of-truth/` と `assets/` への書き込みはブロックされる。
