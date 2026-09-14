import { type FormEvent, useCallback, useEffect, useState } from "react";
import { errorMessage } from "../api/http";
import { cancelJob, createJob, fetchJobLogs, fetchJobs } from "../api/jobs";
import { BusyIndicator } from "../components/BusyIndicator";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { EmptyState } from "../components/EmptyState";
import { ErrorBanner } from "../components/ErrorBanner";
import { formatPercent } from "../domain/format";
import {
  DEFAULT_JOB_PARAMS,
  isLiveJob,
  JOB_STATUS_LABEL,
  type Job,
  type JobCreateParams,
  type JobLogEntry,
} from "../domain/jobs";
import { Link } from "../router/Link";

const POLL_MS = 4000;

type JobRowView = Job & { latestLog: JobLogEntry | null };

async function loadRows(signal?: AbortSignal): Promise<JobRowView[]> {
  const page = await fetchJobs(50, 0, signal);
  const rows: JobRowView[] = [];
  for (const job of page.items) {
    let latestLog: JobLogEntry | null = null;
    if (job.status === "RUNNING") {
      const logs = await fetchJobLogs(job.ref, 200, 0, signal);
      latestLog = logs.items.at(-1) ?? null;
    }
    rows.push({ ...job, latestLog });
  }
  return rows;
}

export function TrainPage() {
  const [jobs, setJobs] = useState<JobRowView[]>([]);
  const [loading, setLoading] = useState(true);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [params, setParams] = useState<JobCreateParams>(DEFAULT_JOB_PARAMS);
  const [cancelRef, setCancelRef] = useState<string | null>(null);

  const refresh = useCallback(async (signal?: AbortSignal) => {
    const rows = await loadRows(signal);
    if (signal?.aborted) {
      return;
    }
    setJobs(rows);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    refresh(controller.signal)
      .then(() => {
        if (!controller.signal.aborted) {
          setError(null);
        }
      })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) {
          setError(errorMessage(reason));
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      });
    return () => {
      controller.abort();
    };
  }, [refresh]);

  const hasLive = jobs.some((job) => isLiveJob(job));

  useEffect(() => {
    if (!hasLive) {
      return;
    }
    const id = window.setInterval(() => {
      refresh().catch((reason: unknown) => {
        setError(errorMessage(reason));
      });
    }, POLL_MS);
    return () => {
      window.clearInterval(id);
    };
  }, [hasLive, refresh]);

  const busy = loading || pending;

  const onStart = (event: FormEvent) => {
    event.preventDefault();
    if (pending) {
      return;
    }
    setPending(true);
    createJob(params)
      .then(async (job) => {
        setNotice(
          `学習ジョブ ${job.ref} を登録しました（${JOB_STATUS_LABEL[job.status]}）。`,
        );
        await refresh();
        setError(null);
      })
      .catch((reason: unknown) => {
        setError(errorMessage(reason));
      })
      .finally(() => {
        setPending(false);
      });
  };

  const onConfirmCancel = () => {
    if (cancelRef === null || pending) {
      return;
    }
    const ref = cancelRef;
    setPending(true);
    cancelJob(ref)
      .then(async () => {
        setCancelRef(null);
        setNotice("学習ジョブを中止しました。");
        await refresh();
        setError(null);
      })
      .catch((reason: unknown) => {
        setError(errorMessage(reason));
      })
      .finally(() => {
        setPending(false);
      });
  };

  const empty = !loading && jobs.length === 0;

  return (
    <article className="page page--wide" data-testid="train-page">
      <h1>学習</h1>
      <p className="lede">
        パラメータを指定して学習を開始します。実行中・待機中の進捗は手動再読み込みなしに
        5 秒以内で更新します。同時に実行できる学習は 1 件です。
      </p>
      {error !== null ? (
        <ErrorBanner message={error} onDismiss={() => setError(null)} />
      ) : null}
      {notice !== null ? (
        <p className="banner banner--info" role="status">
          {notice}
        </p>
      ) : null}
      <BusyIndicator
        pending={busy}
        label={
          pending ? "学習ジョブを更新しています" : "学習ジョブを読み込み中です"
        }
      />

      <section aria-labelledby="start-heading">
        <h2 id="start-heading">開始</h2>
        <form className="split-form" onSubmit={onStart}>
          <label>
            エポック数
            <input
              type="number"
              min={1}
              max={1000}
              value={params.epochs}
              onChange={(event) => {
                setParams((current) => ({
                  ...current,
                  epochs: Number(event.target.value),
                }));
              }}
              data-testid="train-epochs"
            />
          </label>
          <label>
            バッチ数
            <input
              type="number"
              min={1}
              max={512}
              value={params.batch_size}
              onChange={(event) => {
                setParams((current) => ({
                  ...current,
                  batch_size: Number(event.target.value),
                }));
              }}
              data-testid="train-batch"
            />
          </label>
          <label>
            学習率
            <input
              type="number"
              min={0}
              step={0.0001}
              value={params.learning_rate}
              onChange={(event) => {
                setParams((current) => ({
                  ...current,
                  learning_rate: Number(event.target.value),
                }));
              }}
              data-testid="train-lr"
            />
          </label>
          <label>
            乱数シード
            <input
              type="number"
              value={params.seed}
              onChange={(event) => {
                setParams((current) => ({
                  ...current,
                  seed: Number(event.target.value),
                }));
              }}
              data-testid="train-seed"
            />
          </label>
          <label className="check-label">
            <input
              type="checkbox"
              checked={params.augmentation}
              onChange={(event) => {
                setParams((current) => ({
                  ...current,
                  augmentation: event.target.checked,
                }));
              }}
              data-testid="train-aug"
            />
            データ拡張する
          </label>
          <label className="check-label">
            <input
              type="checkbox"
              checked={params.use_baseline}
              onChange={(event) => {
                setParams((current) => ({
                  ...current,
                  use_baseline: event.target.checked,
                }));
              }}
              data-testid="train-baseline"
            />
            ベースラインを利用する
          </label>
          <p>
            <button type="submit" disabled={pending} data-testid="train-start">
              学習を開始
            </button>
          </p>
        </form>
        <p className="muted">
          既定値はエポック 10、バッチ 32、学習率 0.001、シード
          42、拡張あり、ベースライン利用ありです。開始前に
          <Link to="/splits">分割</Link>
          で訓練・検証に確定ラベルが必要です。
        </p>
      </section>

      <section aria-labelledby="jobs-heading">
        <h2 id="jobs-heading">ジョブ</h2>
        {empty ? (
          <EmptyState title="学習ジョブはありません">
            <p>
              上の既定値のまま開始できます。ラベル付き画像を
              <Link to="/splits">分割</Link>
              したあとで実行してください。中止は取り消しできないため、実行前に確認します。
            </p>
          </EmptyState>
        ) : (
          <table data-testid="job-table">
            <caption>新しい順の学習ジョブ</caption>
            <thead>
              <tr>
                <th scope="col">状態</th>
                <th scope="col">進捗</th>
                <th scope="col">訓練損失</th>
                <th scope="col">検証正解率</th>
                <th scope="col">操作</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((job) => (
                <tr key={job.ref} data-testid={`job-row-${job.ref}`}>
                  <th scope="row">
                    <span data-testid={`job-status-${job.ref}`}>
                      {JOB_STATUS_LABEL[job.status]}
                    </span>
                    <div className="muted">
                      <Link to={`/train/${job.ref}`}>{job.ref}</Link>
                    </div>
                  </th>
                  <td data-testid={`job-epoch-${job.ref}`}>
                    {String(job.current_epoch)} / {String(job.total_epochs)}
                  </td>
                  <td data-testid={`job-loss-${job.ref}`}>
                    {job.latestLog === null
                      ? "—"
                      : job.latestLog.train_loss.toFixed(4)}
                  </td>
                  <td data-testid={`job-val-acc-${job.ref}`}>
                    {job.latestLog === null
                      ? "—"
                      : formatPercent(job.latestLog.val_accuracy)}
                  </td>
                  <td>
                    {isLiveJob(job) ? (
                      <button
                        type="button"
                        className="button--danger"
                        onClick={() => {
                          setCancelRef(job.ref);
                        }}
                        disabled={pending}
                        data-testid={`job-cancel-${job.ref}`}
                      >
                        中止
                      </button>
                    ) : job.model_ref !== null ? (
                      <Link to="/models">モデル</Link>
                    ) : (
                      "—"
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <ConfirmDialog
        open={cancelRef !== null}
        title="この学習ジョブを中止しますか？"
        message="中止するとモデル版は生成されません。この操作は取り消せません。"
        confirmLabel="中止する"
        pending={pending}
        onCancel={() => {
          if (!pending) {
            setCancelRef(null);
          }
        }}
        onConfirm={onConfirmCancel}
      />
    </article>
  );
}
