import { type FormEvent, useEffect, useState } from "react";
import { errorMessage } from "../api/http";
import { createSplit } from "../api/splits";
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

export function SplitsPage() {
  const [stats, setStats] = useState<Stats>(EMPTY_STATS);
  const [loading, setLoading] = useState(true);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [train, setTrain] = useState("0.7");
  const [val, setVal] = useState("0.15");
  const [test, setTest] = useState("0.15");
  const [seed, setSeed] = useState("42");

  const busy = loading || pending;

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

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (pending) {
      return;
    }
    const trainRatio = Number(train);
    const valRatio = Number(val);
    const testRatio = Number(test);
    const seedValue = Number(seed);
    if (
      ![trainRatio, valRatio, testRatio, seedValue].every((value) =>
        Number.isFinite(value),
      )
    ) {
      setError("比率とシードは数値で指定してください。");
      return;
    }
    const sum = trainRatio + valRatio + testRatio;
    if (Math.abs(sum - 1) > 1e-9) {
      setError("訓練・検証・試験の比率の合計は 1 にしてください。");
      return;
    }
    setPending(true);
    setError(null);
    createSplit({
      train_ratio: trainRatio,
      val_ratio: valRatio,
      test_ratio: testRatio,
      seed: seedValue,
    })
      .then(async (result) => {
        const next = await fetchStats();
        setStats(next);
        setNotice(
          `確定ラベル ${String(result.assigned_count)} 件を分割しました。未ラベル ${String(result.unassigned_count)} 件は未割当のままです。`,
        );
      })
      .catch((reason: unknown) => {
        setError(errorMessage(reason));
      })
      .finally(() => {
        setPending(false);
      });
  };

  const labeledEmpty = !loading && stats.labeled_count === 0;

  return (
    <article className="page" data-testid="splits-page">
      <h1>分割</h1>
      <p className="lede">
        確定ラベル付き画像を訓練・検証・試験へ層化分割します。未ラベルは未割当のままです。既定は
        0.7 / 0.15 / 0.15、シード 42 です。
      </p>
      {error !== null ? (
        <ErrorBanner message={error} onDismiss={() => setError(null)} />
      ) : null}
      {notice !== null ? (
        <p
          className="banner banner--info"
          role="status"
          data-testid="split-notice"
        >
          {notice}
        </p>
      ) : null}
      <BusyIndicator
        pending={busy}
        label={pending ? "分割を実行しています" : "件数を読み込み中です"}
      />

      <section aria-labelledby="stats-heading">
        <h2 id="stats-heading">件数</h2>
        <dl className="stat-grid">
          <div>
            <dt>総画像</dt>
            <dd data-testid="split-image-count">{stats.image_count}</dd>
          </div>
          <div>
            <dt>確定ラベル</dt>
            <dd data-testid="split-labeled-count">{stats.labeled_count}</dd>
          </div>
          <div>
            <dt>未ラベル</dt>
            <dd>{stats.unlabeled_count}</dd>
          </div>
        </dl>
        <table>
          <caption>分割別件数</caption>
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
                <td data-testid={`split-count-${id}`}>
                  {countForSplit(stats, id)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <table>
          <caption>クラス別の確定ラベル件数</caption>
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

      {labeledEmpty ? (
        <EmptyState title="分割できるラベル付き画像がありません">
          <p>
            先に<Link to="/annotate">アノテーション</Link>
            で確定ラベルを付けてから、この画面で分割してください。サンプルから始める場合は
            <Link to="/">概況</Link>
            の投入を使えます。
          </p>
        </EmptyState>
      ) : (
        <section aria-labelledby="run-heading">
          <h2 id="run-heading">分割の実行</h2>
          <form className="split-form" onSubmit={onSubmit}>
            <label>
              訓練比率
              <input
                type="number"
                min={0}
                max={1}
                step="0.01"
                value={train}
                onChange={(event) => setTrain(event.target.value)}
                disabled={pending}
                data-testid="split-train"
              />
            </label>
            <label>
              検証比率
              <input
                type="number"
                min={0}
                max={1}
                step="0.01"
                value={val}
                onChange={(event) => setVal(event.target.value)}
                disabled={pending}
                data-testid="split-val"
              />
            </label>
            <label>
              試験比率
              <input
                type="number"
                min={0}
                max={1}
                step="0.01"
                value={test}
                onChange={(event) => setTest(event.target.value)}
                disabled={pending}
                data-testid="split-test"
              />
            </label>
            <label>
              乱数シード
              <input
                type="number"
                step="1"
                value={seed}
                onChange={(event) => setSeed(event.target.value)}
                disabled={pending}
                data-testid="split-seed"
              />
            </label>
            <p>
              <button type="submit" disabled={pending} data-testid="split-run">
                分割を実行
              </button>
            </p>
          </form>
        </section>
      )}
    </article>
  );
}
