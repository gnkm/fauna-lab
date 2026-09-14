import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiError, errorMessage } from "../api/http";
import { fetchImages } from "../api/images";
import {
  fetchInferences,
  inferFiles,
  inferRegistered,
} from "../api/inferences";
import { fetchStats } from "../api/stats";
import { BusyIndicator } from "../components/BusyIndicator";
import { Dropzone } from "../components/Dropzone";
import { EmptyState } from "../components/EmptyState";
import { ErrorBanner } from "../components/ErrorBanner";
import { ThumbnailCard } from "../components/ThumbnailCard";
import { displayNameFor } from "../domain/classes";
import { formatPercent } from "../domain/format";
import { EMPTY_FILTERS, type ImageItem } from "../domain/images";
import {
  type Inference,
  MAX_INFERENCE_IMAGES,
  topScores,
} from "../domain/inferences";
import { EMPTY_STATS, type Stats } from "../domain/stats";
import { Link } from "../router/Link";
import { useRouter } from "../router/Router";

function noActiveModelMessage(reason: unknown, stats: Stats): string {
  if (reason instanceof ApiError && reason.code === "no_active_model") {
    return `${reason.message} ${missingModelHint(stats)}`;
  }
  return errorMessage(reason);
}

function missingModelHint(stats: Stats): string {
  if (stats.baseline_registered) {
    return "ベースラインは登録済みです。モデル画面で有効化してください。";
  }
  return "配布資産が無い、または学習済モデルがまだ無い可能性があります。";
}

function ResultList({ items }: { items: Inference[] }) {
  if (items.length === 0) {
    return null;
  }
  return (
    <ol className="infer-results" data-testid="infer-results">
      {items.map((item) => {
        const top3 = topScores(item, 3);
        return (
          <li key={item.ref} data-testid={`infer-item-${item.ref}`}>
            <p>
              最上位: {displayNameFor(item.top_class_id)}{" "}
              <strong>{formatPercent(item.top_confidence)}</strong>
              {item.low_confidence ? " （低信頼）" : ""}
            </p>
            <p className="muted">
              画像{" "}
              <Link to={`/images/${item.image_ref}`}>{item.image_ref}</Link>
            </p>
            <ol className="infer-top3">
              {top3.map((score, index) => (
                <li key={score.class_id}>
                  {index + 1}位 {displayNameFor(score.class_id)}{" "}
                  {formatPercent(score.confidence)}
                </li>
              ))}
            </ol>
          </li>
        );
      })}
    </ol>
  );
}

export function InferPage() {
  const { navigate } = useRouter();
  const [stats, setStats] = useState<Stats>(EMPTY_STATS);
  const [images, setImages] = useState<ImageItem[]>([]);
  const [history, setHistory] = useState<Inference[]>([]);
  const [latest, setLatest] = useState<Inference[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async (signal?: AbortSignal) => {
    const [nextStats, imagePage, inferencePage] = await Promise.all([
      fetchStats(signal),
      fetchImages(EMPTY_FILTERS, 50, 0, signal),
      fetchInferences(50, 0, signal),
    ]);
    if (signal?.aborted) {
      return;
    }
    setStats(nextStats);
    setImages(imagePage.items);
    setHistory(inferencePage.items);
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

  const busy = loading || pending;
  const selectedRefs = useMemo(() => Array.from(selected), [selected]);
  const noModel = stats.active_model === null;

  const run = (work: () => Promise<Inference[]>) => {
    if (pending) {
      return;
    }
    setPending(true);
    work()
      .then(async (items) => {
        setLatest(items);
        await refresh();
        setError(null);
      })
      .catch((reason: unknown) => {
        setLatest([]);
        setError(noActiveModelMessage(reason, stats));
      })
      .finally(() => {
        setPending(false);
      });
  };

  const onFiles = (files: File[]) => {
    if (files.length > MAX_INFERENCE_IMAGES) {
      setError(`1 回の推論は ${String(MAX_INFERENCE_IMAGES)} 件までです。`);
      return;
    }
    run(() => inferFiles(files));
  };

  const onRegistered = () => {
    if (selectedRefs.length === 0) {
      setError("登録済画像を 1 件以上選んでください。");
      return;
    }
    if (selectedRefs.length > MAX_INFERENCE_IMAGES) {
      setError(`1 回の推論は ${String(MAX_INFERENCE_IMAGES)} 件までです。`);
      return;
    }
    run(() => inferRegistered(selectedRefs));
  };

  const toggle = (ref: string) => {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(ref)) {
        next.delete(ref);
      } else {
        next.add(ref);
      }
      return next;
    });
  };

  return (
    <article className="page page--wide" data-testid="infer-page">
      <h1>推論</h1>
      <p className="lede">
        新規ファイルと登録済画像のどちらからでも分類できます。結果は最上位クラスと信頼度（百分率・小数第
        1 位）、上位 3 クラスを示します。
      </p>
      {error !== null ? (
        <ErrorBanner message={error} onDismiss={() => setError(null)} />
      ) : null}
      <BusyIndicator
        pending={busy}
        label={pending ? "推論しています" : "推論画面を読み込み中です"}
      />

      {noModel ? (
        <p
          className="banner banner--error"
          role="status"
          data-testid="infer-no-model"
        >
          有効モデルがありません。{missingModelHint(stats)}
          <Link to="/models">モデル</Link>
          または
          <Link to="/">概況</Link>
          を確認してください。ベースラインがあれば学習前でも推論できます。
        </p>
      ) : (
        <p data-testid="infer-active-model">
          有効モデルは{stats.active_model?.builtin ? "ベースライン" : "学習済"}
          （版 {String(stats.active_model?.version ?? "—")}）です。
        </p>
      )}

      <section aria-labelledby="new-file-heading">
        <h2 id="new-file-heading">新規ファイル</h2>
        <Dropzone disabled={busy || noModel} onFiles={onFiles} />
        <p className="muted">
          1 回あたり最大 {String(MAX_INFERENCE_IMAGES)} 件です。
        </p>
      </section>

      <section aria-labelledby="registered-heading">
        <h2 id="registered-heading">登録済画像</h2>
        {images.length === 0 ? (
          <EmptyState title="登録済画像がありません">
            <p>
              <Link to="/images">画像</Link>
              から登録するか、
              <Link to="/">概況</Link>
              でサンプルを投入してください。
            </p>
          </EmptyState>
        ) : (
          <>
            <p>
              <button
                type="button"
                onClick={onRegistered}
                disabled={busy || noModel || selectedRefs.length === 0}
                data-testid="infer-registered"
              >
                選択した登録済画像を推論（{String(selectedRefs.length)}）
              </button>
            </p>
            <div className="thumb-grid">
              {images.map((image) => (
                <ThumbnailCard
                  key={image.ref}
                  image={image}
                  selected={selected.has(image.ref)}
                  onToggle={() => {
                    toggle(image.ref);
                  }}
                  onOpen={() => navigate(`/images/${image.ref}`)}
                />
              ))}
            </div>
          </>
        )}
      </section>

      <section aria-labelledby="latest-heading">
        <h2 id="latest-heading">直前の結果</h2>
        {latest.length === 0 ? (
          <p className="muted">この画面でまだ推論していません。</p>
        ) : (
          <ResultList items={latest} />
        )}
      </section>

      <section aria-labelledby="history-heading">
        <h2 id="history-heading">履歴</h2>
        {history.length === 0 ? (
          <EmptyState title="推論履歴はありません">
            <p>
              有効モデルで画像を分類し、結果と履歴を確認します。ベースラインがあれば学習前でも実行できます。
            </p>
          </EmptyState>
        ) : (
          <ResultList items={history} />
        )}
      </section>
    </article>
  );
}
