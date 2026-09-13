import { useEffect, useState } from "react";
import { errorMessage } from "../api/http";
import { deleteImage, fetchImage } from "../api/images";
import { deleteImageLabel, putImageLabel } from "../api/labels";
import { BusyIndicator } from "../components/BusyIndicator";
import { ClassSelect } from "../components/ClassSelect";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { EmptyState } from "../components/EmptyState";
import { ErrorBanner } from "../components/ErrorBanner";
import { displayNameFor, SPLIT_LABELS } from "../domain/classes";
import type { ClassId, ImageItem } from "../domain/images";
import { thumbnailUrl, withLabel } from "../domain/images";
import { Link } from "../router/Link";
import { useRouter } from "../router/Router";

export function ImageDetailPage() {
  const { match, navigate } = useRouter();
  const ref = match.params.ref ?? "";
  const [image, setImage] = useState<ImageItem | null>(null);
  const [missing, setMissing] = useState(false);
  const [loading, setLoading] = useState(true);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [classId, setClassId] = useState<ClassId | "">("");

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setMissing(false);
    fetchImage(ref, controller.signal)
      .then((next) => {
        setImage(next);
        setClassId(next.label?.class_id ?? "");
        setError(null);
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted) {
          return;
        }
        setImage(null);
        setMissing(true);
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
  }, [ref]);

  const busy = loading || pending;

  const onAssign = () => {
    if (pending || classId === "" || image === null) {
      return;
    }
    setPending(true);
    putImageLabel(image.ref, classId)
      .then((label) => {
        setImage(withLabel(image, label));
        setError(null);
      })
      .catch((reason: unknown) => {
        setError(errorMessage(reason));
      })
      .finally(() => {
        setPending(false);
      });
  };

  const onClearLabel = () => {
    if (pending || image === null) {
      return;
    }
    setPending(true);
    deleteImageLabel(image.ref)
      .then(() => {
        setImage(withLabel(image, null));
        setClassId("");
        setError(null);
      })
      .catch((reason: unknown) => {
        setError(errorMessage(reason));
      })
      .finally(() => {
        setPending(false);
      });
  };

  const onConfirmDelete = () => {
    if (pending) {
      return;
    }
    setPending(true);
    deleteImage(ref)
      .then(() => {
        navigate("/images");
      })
      .catch((reason: unknown) => {
        setError(errorMessage(reason));
        setConfirmOpen(false);
      })
      .finally(() => {
        setPending(false);
      });
  };

  if (!loading && (missing || image === null)) {
    return (
      <article className="page">
        <h1>画像の詳細</h1>
        {error !== null ? (
          <ErrorBanner message={error} onDismiss={() => setError(null)} />
        ) : null}
        <EmptyState title="この画像は表示できません">
          <p>
            識別子 <code>{ref}</code>{" "}
            の画像が見つからないか、まだ登録されていません。
          </p>
          <p>
            <Link to="/images">画像一覧</Link>
            に戻って、登録済みの画像を選んでください。
          </p>
        </EmptyState>
      </article>
    );
  }

  return (
    <article className="page" data-testid="image-detail-page">
      <h1>画像の詳細</h1>
      {error !== null ? (
        <ErrorBanner message={error} onDismiss={() => setError(null)} />
      ) : null}
      <BusyIndicator
        pending={busy}
        label={pending ? "処理しています" : "画像を読み込み中です"}
      />
      {image !== null ? (
        <>
          <p>
            <Link to="/images">画像一覧</Link>
            {" · "}
            <Link to="/annotate">アノテーション</Link>
          </p>
          <figure className="detail-figure">
            <img src={thumbnailUrl(image.ref)} alt={image.original_name} />
            <figcaption>{image.original_name}</figcaption>
          </figure>
          <dl className="detail-list">
            <div>
              <dt>識別子</dt>
              <dd>
                <code>{image.ref}</code>
              </dd>
            </div>
            <div>
              <dt>SHA-256</dt>
              <dd>
                <code>{image.sha256}</code>
              </dd>
            </div>
            <div>
              <dt>大きさ</dt>
              <dd>
                {String(image.width)} × {String(image.height)} /{" "}
                {String(image.size_bytes)} バイト
              </dd>
            </div>
            <div>
              <dt>分割</dt>
              <dd>{SPLIT_LABELS[image.split]}</dd>
            </div>
            <div>
              <dt>確定ラベル</dt>
              <dd>
                {image.label !== null ? (
                  <span className="badge badge--label">
                    {displayNameFor(image.label.class_id)}（
                    {image.label.source === "human" ? "人手" : "候補の採用"}）
                  </span>
                ) : (
                  <span className="badge badge--none">未ラベル</span>
                )}
              </dd>
            </div>
            <div>
              <dt>候補ラベル</dt>
              <dd>
                {image.suggestion !== null ? (
                  <span className="badge badge--suggestion">
                    {displayNameFor(image.suggestion.class_id)}（
                    {image.suggestion.confidence.toFixed(2)}）
                  </span>
                ) : (
                  "なし"
                )}
              </dd>
            </div>
          </dl>
          <section aria-labelledby="label-heading">
            <h2 id="label-heading">確定ラベル</h2>
            <div className="form-row">
              <ClassSelect
                value={classId}
                onChange={setClassId}
                disabled={pending}
              />
              <button
                type="button"
                onClick={onAssign}
                disabled={pending || classId === ""}
              >
                付与する
              </button>
              <button
                type="button"
                onClick={onClearLabel}
                disabled={pending || image.label === null}
              >
                ラベルを解除
              </button>
            </div>
          </section>
          <section aria-labelledby="delete-heading">
            <h2 id="delete-heading">削除</h2>
            <p>削除は取り消しできません。実行前に確認します。</p>
            <p>
              <button
                type="button"
                className="button--danger"
                onClick={() => setConfirmOpen(true)}
                disabled={pending}
              >
                この画像を削除
              </button>
            </p>
          </section>
        </>
      ) : null}
      <ConfirmDialog
        open={confirmOpen}
        title="この画像を削除しますか？"
        message="画像とラベル、候補、推論履歴、ファイルを削除します。学習済モデル版は残ります。"
        confirmLabel="削除する"
        pending={pending}
        onCancel={() => {
          if (!pending) {
            setConfirmOpen(false);
          }
        }}
        onConfirm={onConfirmDelete}
      />
    </article>
  );
}
