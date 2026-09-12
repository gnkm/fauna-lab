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

- 技術スタックと実行形態は `docs/ARCHITECTURE.md` を正とする（Python 3.12 / FastAPI / SQLite / Vite、実行は Podman、Cloud では同一 OCI を Docker）。
- Cloud の依存準備は `.cursor/environment.json` の `install` で行う（現状: `pnpm install`。Python 骨格と lockfile が追加されたら更新する）。
- 長時間常駐プロセスは `install` に置かず、必要になったら `start` / `terminals` に追加する。

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
