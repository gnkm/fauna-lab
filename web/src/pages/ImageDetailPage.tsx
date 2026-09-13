import { useState } from "react";
import { errorMessage, readProblem } from "../api/http";
import { BusyIndicator } from "../components/BusyIndicator";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { EmptyState } from "../components/EmptyState";
import { ErrorBanner } from "../components/ErrorBanner";
import { Link } from "../router/Link";
import { useRouter } from "../router/Router";

export function ImageDetailPage() {
  const { match, navigate } = useRouter();
  const ref = match.params.ref ?? "";
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onConfirm = () => {
    if (pending) {
      return;
    }
    setPending(true);
    fetch(`/api/images/${encodeURIComponent(ref)}`, { method: "DELETE" })
      .then(async (response) => {
        if (response.status === 204 || response.ok) {
          navigate("/images");
          return;
        }
        throw await readProblem(response);
      })
      .catch((reason: unknown) => {
        setError(errorMessage(reason));
        setConfirmOpen(false);
      })
      .finally(() => {
        setPending(false);
      });
  };

  return (
    <article className="page">
      <h1>画像の詳細</h1>
      {error !== null ? (
        <ErrorBanner message={error} onDismiss={() => setError(null)} />
      ) : null}
      <BusyIndicator pending={pending} label="画像を削除しています" />
      <EmptyState title="この画像は表示できません">
        <p>
          識別子 <code>{ref}</code>{" "}
          の画像が見つからないか、まだ登録されていません。
        </p>
        <p>
          <Link to="/images">画像一覧</Link>
          に戻って、登録済みの画像を選んでください。
        </p>
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
      </EmptyState>
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
        onConfirm={onConfirm}
      />
    </article>
  );
}
