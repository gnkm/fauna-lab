import { useCallback, useEffect, useState } from "react";
import { ApiError, errorMessage } from "../api/http";
import { cancelJob, fetchJob, fetchJobLogs } from "../api/jobs";
import { BusyIndicator } from "../components/BusyIndicator";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { EmptyState } from "../components/EmptyState";
import { ErrorBanner } from "../components/ErrorBanner";
import { formatPercent } from "../domain/format";
import {
  isLiveJob,
  JOB_STATUS_LABEL,
  type Job,
  type JobLogEntry,
} from "../domain/jobs";
import { useLatestRequest, useLivePoll } from "../hooks/useLivePoll";
import { Link } from "../router/Link";
import { useRouter } from "../router/Router";

const POLL_MS = 4000;

export function TrainJobPage() {
  const { match } = useRouter();
  const ref = match.params.ref ?? "";
  const [job, setJob] = useState<Job | null>(null);
  const [logs, setLogs] = useState<JobLogEntry[]>([]);
  const [missing, setMissing] = useState(false);
  const [loading, setLoading] = useState(true);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const beginRequest = useLatestRequest();

  const refresh = useCallback(
    async (signal?: AbortSignal) => {
      const { isCurrent } = beginRequest();
      const next = await fetchJob(ref, signal);
      if (signal?.aborted || !isCurrent()) {
        return;
      }
      if (next === null) {
        setJob(null);
        setMissing(true);
        setLogs([]);
        return;
      }
      const page = await fetchJobLogs(ref, 200, 0, signal);
      if (signal?.aborted || !isCurrent()) {
        return;
      }
      setJob(next);
      setLogs(page.items);
      setMissing(false);
    },
    [beginRequest, ref],
  );

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
        if (controller.signal.aborted) {
          return;
        }
        if (reason instanceof ApiError && reason.status === 404) {
          setMissing(true);
          setJob(null);
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
  }, [refresh]);

  const live = job !== null && isLiveJob(job);

  useLivePoll(live, POLL_MS, refresh, (reason) => {
    setError(errorMessage(reason));
  });

  const onConfirmCancel = () => {
    if (pending || job === null) {
      return;
    }
    setPending(true);
    cancelJob(job.ref)
      .then(async () => {
        setConfirmOpen(false);
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

  if (missing && !loading) {
    return (
      <article className="page">
        <h1>学習ジョブ</h1>
        <EmptyState title="この学習ジョブは表示できません">
          <p>
            識別子 <code>{ref}</code>{" "}
            のジョブが見つからないか、まだ開始されていません。
          </p>
          <p>
            <Link to="/train">学習</Link>
            に戻って、開始済みのジョブを選んでください。
          </p>
        </EmptyState>
      </article>
    );
  }

  const latest = logs.at(-1) ?? null;

  return (
    <article className="page page--wide" data-testid="train-job-page">
      <h1>学習ジョブ</h1>
      <p className="lede">
        <Link to="/train">学習一覧</Link>
        に戻る。実行中は進捗とログが自動更新されます。
      </p>
      {error !== null ? (
        <ErrorBanner message={error} onDismiss={() => setError(null)} />
      ) : null}
      <BusyIndicator
        pending={loading || pending}
        label="ジョブを読み込み中です"
      />
      {job !== null ? (
        <>
          <dl className="detail-list">
            <div>
              <dt>識別子</dt>
              <dd>
                <code>{job.ref}</code>
              </dd>
            </div>
            <div>
              <dt>状態</dt>
              <dd data-testid="job-detail-status">
                {JOB_STATUS_LABEL[job.status]}
              </dd>
            </div>
            <div>
              <dt>進捗</dt>
              <dd data-testid="job-detail-epoch">
                {String(job.current_epoch)} / {String(job.total_epochs)}
              </dd>
            </div>
            <div>
              <dt>直近の訓練損失</dt>
              <dd>{latest === null ? "—" : latest.train_loss.toFixed(4)}</dd>
            </div>
            <div>
              <dt>直近の検証正解率</dt>
              <dd>
                {latest === null ? "—" : formatPercent(latest.val_accuracy)}
              </dd>
            </div>
            <div>
              <dt>生成モデル</dt>
              <dd>
                {job.model_ref === null ? (
                  "—"
                ) : (
                  <Link to="/models">{job.model_ref}</Link>
                )}
              </dd>
            </div>
          </dl>
          {isLiveJob(job) ? (
            <p>
              <button
                type="button"
                className="button--danger"
                onClick={() => {
                  setConfirmOpen(true);
                }}
                disabled={pending}
              >
                このジョブを中止
              </button>
            </p>
          ) : null}
        </>
      ) : null}

      <section aria-labelledby="log-heading">
        <h2 id="log-heading">ログ</h2>
        {logs.length === 0 ? (
          <p className="muted">エポックログはまだありません。</p>
        ) : (
          <table data-testid="job-log-table">
            <caption>エポック時系列</caption>
            <thead>
              <tr>
                <th scope="col">エポック</th>
                <th scope="col">訓練損失</th>
                <th scope="col">検証損失</th>
                <th scope="col">検証正解率</th>
                <th scope="col">秒</th>
              </tr>
            </thead>
            <tbody>
              {logs.map((entry) => (
                <tr key={entry.epoch}>
                  <th scope="row">{entry.epoch}</th>
                  <td>{entry.train_loss.toFixed(4)}</td>
                  <td>{entry.val_loss.toFixed(4)}</td>
                  <td>{formatPercent(entry.val_accuracy)}</td>
                  <td>{entry.duration_seconds.toFixed(1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <ConfirmDialog
        open={confirmOpen}
        title="この学習ジョブを中止しますか？"
        message="中止するとモデル版は生成されません。この操作は取り消せません。"
        confirmLabel="中止する"
        pending={pending}
        onCancel={() => {
          if (!pending) {
            setConfirmOpen(false);
          }
        }}
        onConfirm={onConfirmCancel}
      />
    </article>
  );
}
