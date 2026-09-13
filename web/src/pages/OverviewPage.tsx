import { useEffect, useState } from "react";
import { errorMessage } from "../api/http";
import { importSample } from "../api/sample";
import { fetchStats } from "../api/stats";
import { BusyIndicator } from "../components/BusyIndicator";
import { EmptyState } from "../components/EmptyState";
import { ErrorBanner } from "../components/ErrorBanner";
import { SPLIT_IDS, SPLIT_LABELS, SYSTEM_CLASSES } from "../domain/classes";
import {
  countForClass,
  countForSplit,
  EMPTY_STATS,
  type Stats,
} from "../domain/stats";
import { Link } from "../router/Link";

export function OverviewPage() {
  const [stats, setStats] = useState<Stats>(EMPTY_STATS);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [importing, setImporting] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    fetchStats(controller.signal)
      .then((next) => {
        setStats(next);
        setError(null);
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted) {
          return;
        }
        setStats(EMPTY_STATS);
        setError(errorMessage(reason));
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      });
    return () => {
      controller.abort();
    };
  }, []);

  const pending = loading || importing;
  const empty = stats.image_count === 0;

  const onImport = () => {
    if (pending) {
      return;
    }
    setImporting(true);
    setError(null);
    importSample()
      .then(async (result) => {
        const next = await fetchStats();
        setStats(next);
        setNotice(
          `サンプル ${String(result.updated_count)} 件を登録しました。`,
        );
      })
      .catch((reason: unknown) => {
        setError(errorMessage(reason));
      })
      .finally(() => {
        setImporting(false);
      });
  };

  return (
    <article className="page" data-testid="overview-page">
      <h1>概況</h1>
      <p className="lede">
        データセットの件数、有効モデル、学習ジョブの有無を確認します。表示はサーバの状態です。この画面は権威ある状態を持ちません。
      </p>
      {error !== null ? (
        <ErrorBanner message={error} onDismiss={() => setError(null)} />
      ) : null}
      {notice !== null ? (
        <p className="banner banner--info" role="status">
          {notice}
        </p>
      ) : null}
      <BusyIndicator pending={pending} label="概況を読み込み中です" />

      <section aria-labelledby="counts-heading">
        <h2 id="counts-heading">件数</h2>
        <dl className="stat-grid">
          <div>
            <dt>総画像</dt>
            <dd data-testid="stat-image-count">{stats.image_count}</dd>
          </div>
          <div>
            <dt>確定ラベル</dt>
            <dd>{stats.labeled_count}</dd>
          </div>
          <div>
            <dt>未ラベル</dt>
            <dd>{stats.unlabeled_count}</dd>
          </div>
          <div>
            <dt>候補ラベル</dt>
            <dd>{stats.suggestion_count}</dd>
          </div>
        </dl>
      </section>

      <section aria-labelledby="class-heading">
        <h2 id="class-heading">クラス別</h2>
        <table>
          <caption>確定ラベルのクラス別件数</caption>
          <thead>
            <tr>
              <th scope="col">クラス</th>
              <th scope="col">件数</th>
            </tr>
          </thead>
          <tbody>
            {SYSTEM_CLASSES.map((item) => (
              <tr key={item.classId}>
                <th scope="row">{item.displayName}</th>
                <td>{countForClass(stats, item.classId)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section aria-labelledby="split-heading">
        <h2 id="split-heading">分割別</h2>
        <table>
          <caption>画像の分割別件数</caption>
          <thead>
            <tr>
              <th scope="col">分割</th>
              <th scope="col">件数</th>
            </tr>
          </thead>
          <tbody>
            {SPLIT_IDS.map((id) => (
              <tr key={id}>
                <th scope="row">{SPLIT_LABELS[id]}</th>
                <td>{countForSplit(stats, id)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section aria-labelledby="model-heading">
        <h2 id="model-heading">有効モデル</h2>
        <ActiveModelPanel stats={stats} />
      </section>

      <section aria-labelledby="job-heading">
        <h2 id="job-heading">学習ジョブ</h2>
        {stats.has_active_job ? (
          <p>
            実行中または待機中の学習ジョブがあります。進捗は
            <Link to="/train">学習</Link>
            画面で確認できます。
          </p>
        ) : (
          <p>実行中および待機中の学習ジョブはありません。</p>
        )}
      </section>

      {empty ? (
        <EmptyState title="データがまだありません">
          <p>
            空白のままにはしません。次の順で進めると、サンプルから推論まで一通り確認できます。
          </p>
          <ol>
            <li>
              下のボタンでサンプルを投入するか、<Link to="/images">画像</Link>
              からファイルを登録する
            </li>
            <li>
              <Link to="/annotate">アノテーション</Link>
              で候補ラベルを生成・採用する
            </li>
            <li>
              <Link to="/splits">分割</Link>して<Link to="/train">学習</Link>
              する（ベースラインがあれば学習前でも推論できます）
            </li>
            <li>
              <Link to="/infer">推論</Link>で結果を確認する
            </li>
          </ol>
          <p>
            <button
              type="button"
              onClick={onImport}
              disabled={pending}
              data-testid="import-sample"
            >
              サンプルデータを投入
            </button>
          </p>
        </EmptyState>
      ) : null}
    </article>
  );
}

function ActiveModelPanel({ stats }: { stats: Stats }) {
  const model = stats.active_model;
  if (model !== null) {
    const kind = model.builtin ? "ベースライン" : "学習済";
    const versionLabel =
      model.version >= 0 ? `版 ${String(model.version)}` : "";
    return (
      <p data-testid="active-model">
        有効モデルは{kind}です。
        {versionLabel !== "" ? `（${versionLabel}）` : null}
        識別子は <code>{model.ref}</code> です。
      </p>
    );
  }
  const reason = missingModelReason(stats);
  return (
    <p data-testid="active-model-missing">有効モデルはありません。{reason}</p>
  );
}

function missingModelReason(stats: Stats): string {
  if (stats.baseline_registered) {
    return "ベースラインは登録されていますが、有効化されていません。モデル画面で有効化してください。";
  }
  return "考えられる原因は、配布資産（ベースライン）がマウントされていないか検証に失敗したこと、または学習済モデルがまだ無いことです。";
}
