import { type FormEvent, useCallback, useEffect, useState } from "react";
import { errorMessage } from "../api/http";
import {
  acceptSuggestions,
  acceptSuggestionsByThreshold,
  fetchSuggestions,
  generateSuggestions,
  rejectSuggestions,
} from "../api/suggestions";
import { displayNameFor } from "../domain/classes";
import { formatPercent } from "../domain/format";
import { thumbnailUrl } from "../domain/images";
import type { SuggestionItem, SuggestionOrder } from "../domain/suggestions";
import { Link } from "../router/Link";
import { BusyIndicator } from "./BusyIndicator";
import { ErrorBanner } from "./ErrorBanner";

export function SuggestionPanel({
  selectedRefs,
  pending: parentPending,
  onChanged,
}: {
  selectedRefs: string[];
  pending: boolean;
  onChanged: () => Promise<void>;
}) {
  const [items, setItems] = useState<SuggestionItem[]>([]);
  const [total, setTotal] = useState(0);
  const [order, setOrder] = useState<SuggestionOrder>("asc");
  const [threshold, setThreshold] = useState("80");
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const busy = loading || working || parentPending;

  const reload = useCallback(
    async (signal?: AbortSignal) => {
      const page = await fetchSuggestions(order, 200, 0, signal);
      setItems(page.items);
      setTotal(page.total);
    },
    [order],
  );

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    reload(controller.signal)
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
  }, [reload]);

  const afterChange = async (message: string) => {
    setNotice(message);
    await reload();
    await onChanged();
    setError(null);
  };

  const onGenerate = () => {
    if (busy) {
      return;
    }
    setWorking(true);
    const refs = selectedRefs.length > 0 ? selectedRefs : undefined;
    generateSuggestions(refs)
      .then(async (result) => {
        await afterChange(
          `候補を ${String(result.generated_count)} 件生成しました。確定ラベル付き ${String(result.skipped_labeled_count)} 件は読み飛ばしました。`,
        );
      })
      .catch((reason: unknown) => {
        setError(errorMessage(reason));
      })
      .finally(() => {
        setWorking(false);
      });
  };

  const onAccept = (imageRef: string) => {
    if (busy) {
      return;
    }
    setWorking(true);
    acceptSuggestions([imageRef])
      .then(async (count) => {
        await afterChange(`候補を ${String(count)} 件採用しました。`);
      })
      .catch((reason: unknown) => {
        setError(errorMessage(reason));
      })
      .finally(() => {
        setWorking(false);
      });
  };

  const onReject = (imageRef: string) => {
    if (busy) {
      return;
    }
    setWorking(true);
    rejectSuggestions([imageRef])
      .then(async (count) => {
        await afterChange(`候補を ${String(count)} 件却下しました。`);
      })
      .catch((reason: unknown) => {
        setError(errorMessage(reason));
      })
      .finally(() => {
        setWorking(false);
      });
  };

  const onThreshold = (event: FormEvent) => {
    event.preventDefault();
    if (busy) {
      return;
    }
    const percent = Number(threshold);
    if (!Number.isFinite(percent) || percent < 0 || percent > 100) {
      setError("閾値は 0 から 100 の百分率で指定してください。");
      return;
    }
    setWorking(true);
    acceptSuggestionsByThreshold(percent / 100)
      .then(async (count) => {
        await afterChange(
          `信頼度 ${threshold}% 以上の候補を ${String(count)} 件採用しました。`,
        );
      })
      .catch((reason: unknown) => {
        setError(errorMessage(reason));
      })
      .finally(() => {
        setWorking(false);
      });
  };

  return (
    <section aria-labelledby="suggest-heading">
      <h2 id="suggest-heading">候補ラベル</h2>
      <p className="muted">
        有効モデルで未ラベル画像の候補を出します。既定の並びは信頼度の昇順（判断が難しい画像から）です。人手の
        1 枚ラベルは必須ではありません。
      </p>
      {error !== null ? (
        <ErrorBanner
          message={error}
          onDismiss={() => {
            setError(null);
          }}
        />
      ) : null}
      {notice !== null ? (
        <p className="banner banner--info" role="status">
          {notice}
        </p>
      ) : null}
      <BusyIndicator
        pending={loading || working}
        label={working ? "候補を更新しています" : "候補を読み込み中です"}
      />
      <div className="form-row">
        <button
          type="button"
          onClick={onGenerate}
          disabled={busy}
          data-testid="suggest-generate"
        >
          {selectedRefs.length > 0
            ? `選択 ${String(selectedRefs.length)} 件から候補を生成`
            : "未ラベルから候補を生成"}
        </button>
        <label>
          並び
          <select
            value={order}
            onChange={(event) => {
              setOrder(event.target.value === "desc" ? "desc" : "asc");
            }}
            disabled={busy}
            data-testid="suggest-order"
          >
            <option value="asc">信頼度の昇順</option>
            <option value="desc">信頼度の降順</option>
          </select>
        </label>
      </div>
      <form className="form-row" onSubmit={onThreshold}>
        <label>
          一括採用の最低信頼度（%）
          <input
            type="number"
            min={0}
            max={100}
            step={0.1}
            value={threshold}
            onChange={(event) => {
              setThreshold(event.target.value);
            }}
            disabled={busy}
            data-testid="suggest-threshold"
          />
        </label>
        <button
          type="submit"
          disabled={busy}
          data-testid="suggest-accept-threshold"
        >
          閾値以上を一括採用
        </button>
      </form>
      <p className="muted">
        有効モデルが無いときは生成に失敗します。<Link to="/models">モデル</Link>
        で有効化するか、<Link to="/">概況</Link>
        の案内を確認してください。
      </p>
      {items.length === 0 && !loading ? (
        <p data-testid="suggest-empty">候補ラベルはまだありません。</p>
      ) : (
        <ul className="suggest-list" data-testid="suggest-list">
          {items.map((item) => (
            <li key={item.image_ref} className="suggest-item">
              <img
                src={thumbnailUrl(item.image_ref)}
                alt=""
                width={96}
                height={96}
              />
              <div>
                <p>
                  候補: {displayNameFor(item.class_id)}{" "}
                  <strong data-testid={`suggest-confidence-${item.image_ref}`}>
                    {formatPercent(item.confidence)}
                  </strong>
                </p>
                <p className="muted">
                  画像 <code>{item.image_ref}</code>
                </p>
                <div className="form-row">
                  <button
                    type="button"
                    onClick={() => {
                      onAccept(item.image_ref);
                    }}
                    disabled={busy}
                    data-testid={`suggest-accept-${item.image_ref}`}
                  >
                    採用
                  </button>
                  <button
                    type="button"
                    className="button--danger"
                    onClick={() => {
                      onReject(item.image_ref);
                    }}
                    disabled={busy}
                    data-testid={`suggest-reject-${item.image_ref}`}
                  >
                    却下
                  </button>
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
      {items.length < total ? (
        <p className="muted">
          先頭 {String(items.length)} 件を表示しています。
        </p>
      ) : null}
    </section>
  );
}
