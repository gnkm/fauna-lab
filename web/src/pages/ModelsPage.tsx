import { useCallback, useEffect, useState } from "react";
import { errorMessage } from "../api/http";
import {
  activateModel,
  deleteModel,
  evaluateModel,
  fetchModels,
} from "../api/models";
import { BusyIndicator } from "../components/BusyIndicator";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { ConfusionMatrixTable } from "../components/ConfusionMatrix";
import { EmptyState } from "../components/EmptyState";
import { ErrorBanner } from "../components/ErrorBanner";
import { formatDateTime, formatPercent } from "../domain/format";
import type { ModelVersion } from "../domain/models";
import { Link } from "../router/Link";

export function ModelsPage() {
  const [models, setModels] = useState<ModelVersion[]>([]);
  const [selectedRef, setSelectedRef] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [deleteRef, setDeleteRef] = useState<string | null>(null);

  const refresh = useCallback(async (signal?: AbortSignal) => {
    const page = await fetchModels(50, 0, signal);
    if (signal?.aborted) {
      return page.items;
    }
    setModels(page.items);
    return page.items;
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    refresh(controller.signal)
      .then((items) => {
        if (controller.signal.aborted) {
          return;
        }
        setSelectedRef((current) => {
          if (current !== null && items.some((item) => item.ref === current)) {
            return current;
          }
          return items[0]?.ref ?? null;
        });
        setError(null);
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

  const selected = models.find((item) => item.ref === selectedRef) ?? null;
  const busy = loading || pending;

  const onActivate = (ref: string) => {
    if (pending) {
      return;
    }
    setPending(true);
    activateModel(ref)
      .then(async () => {
        setNotice("モデルを有効化しました。");
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

  const onEvaluate = (ref: string) => {
    if (pending) {
      return;
    }
    setPending(true);
    evaluateModel(ref)
      .then(async () => {
        setNotice("試験用分割で再評価しました。");
        const items = await refresh();
        setSelectedRef(ref);
        if (items.some((item) => item.ref === ref)) {
          setError(null);
        }
      })
      .catch((reason: unknown) => {
        setError(errorMessage(reason));
      })
      .finally(() => {
        setPending(false);
      });
  };

  const onConfirmDelete = () => {
    if (deleteRef === null || pending) {
      return;
    }
    const ref = deleteRef;
    setPending(true);
    deleteModel(ref)
      .then(async () => {
        setDeleteRef(null);
        setNotice("モデル版を削除しました。");
        const items = await refresh();
        setSelectedRef((current) =>
          current === ref ? (items[0]?.ref ?? null) : current,
        );
        setError(null);
      })
      .catch((reason: unknown) => {
        setError(errorMessage(reason));
      })
      .finally(() => {
        setPending(false);
      });
  };

  const empty = !loading && models.length === 0;

  return (
    <article className="page page--wide" data-testid="models-page">
      <h1>モデル</h1>
      <p className="lede">
        版番号、作成日時、試験正解率、有効かどうかを確認します。版 0
        は内蔵のベースラインで、削除操作は出しません。
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
        label={pending ? "モデルを更新しています" : "モデルを読み込み中です"}
      />

      {empty ? (
        <EmptyState title="操作できるモデル版がまだ並びません">
          <p>
            配布資産が無いと版 0 は登録されません。学習済モデルが無い場合は
            <Link to="/train">学習</Link>
            から作成します。有効モデルが無いときは
            <Link to="/infer">推論</Link>
            も候補生成もできません。
          </p>
        </EmptyState>
      ) : (
        <table data-testid="model-table">
          <caption>モデル版（新しい版が上）</caption>
          <thead>
            <tr>
              <th scope="col">版</th>
              <th scope="col">作成日時</th>
              <th scope="col">試験正解率</th>
              <th scope="col">有効</th>
              <th scope="col">操作</th>
            </tr>
          </thead>
          <tbody>
            {models.map((model) => {
              const canDelete = !model.builtin && !model.active;
              return (
                <tr
                  key={model.ref}
                  data-testid={`model-row-${model.ref}`}
                  className={
                    model.ref === selectedRef ? "row--selected" : undefined
                  }
                >
                  <th scope="row">
                    <button
                      type="button"
                      className="linkish"
                      onClick={() => {
                        setSelectedRef(model.ref);
                      }}
                    >
                      版 {String(model.version)}
                      {model.builtin ? "（内蔵）" : ""}
                    </button>
                  </th>
                  <td>{formatDateTime(model.created_at)}</td>
                  <td>
                    {model.metrics === null
                      ? "—"
                      : formatPercent(model.metrics.accuracy)}
                  </td>
                  <td>{model.active ? "有効" : "—"}</td>
                  <td>
                    <div className="form-row">
                      <button
                        type="button"
                        onClick={() => {
                          onActivate(model.ref);
                        }}
                        disabled={pending || model.active}
                        data-testid={`model-activate-${model.ref}`}
                      >
                        有効化
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          onEvaluate(model.ref);
                        }}
                        disabled={pending}
                        data-testid={`model-evaluate-${model.ref}`}
                      >
                        再評価
                      </button>
                      {canDelete ? (
                        <button
                          type="button"
                          className="button--danger"
                          onClick={() => {
                            setDeleteRef(model.ref);
                          }}
                          disabled={pending}
                          data-testid={`model-delete-${model.ref}`}
                        >
                          削除
                        </button>
                      ) : null}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}

      {selected !== null ? (
        <section aria-labelledby="selected-model-heading">
          <h2 id="selected-model-heading">
            版 {String(selected.version)}
            {selected.builtin ? "（内蔵）" : ""}
          </h2>
          <p className="muted">
            識別子 <code>{selected.ref}</code>
            {selected.active ? " ・ 現在の有効モデル" : ""}
          </p>
          {selected.metrics === null ? (
            <p data-testid="metrics-missing">
              試験指標はまだありません。試験用分割に確定ラベルがある状態で再評価してください。
            </p>
          ) : (
            <>
              <p data-testid="model-accuracy">
                試験正解率 {formatPercent(selected.metrics.accuracy)}
              </p>
              <ConfusionMatrixTable metrics={selected.metrics} />
            </>
          )}
          <p>
            有効モデルは<Link to="/infer">推論</Link>
            と候補生成に使われます。
          </p>
        </section>
      ) : null}

      <ConfirmDialog
        open={deleteRef !== null}
        title="このモデル版を削除しますか？"
        message="削除すると一覧から外れます。有効モデルと版 0 は削除できません。"
        confirmLabel="削除する"
        pending={pending}
        onCancel={() => {
          if (!pending) {
            setDeleteRef(null);
          }
        }}
        onConfirm={onConfirmDelete}
      />
    </article>
  );
}
