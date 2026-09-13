import { useEffect, useId, useRef } from "react";

export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel,
  pending = false,
  onCancel,
  onConfirm,
}: {
  open: boolean;
  title: string;
  message: string;
  confirmLabel: string;
  pending?: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const titleId = useId();

  useEffect(() => {
    const dialog = dialogRef.current;
    if (dialog === null) {
      return;
    }
    if (open) {
      if (!dialog.open) {
        dialog.showModal();
      }
    } else if (dialog.open) {
      dialog.close();
    }
  }, [open]);

  return (
    <dialog
      ref={dialogRef}
      className="confirm"
      aria-labelledby={titleId}
      onCancel={(event) => {
        event.preventDefault();
        if (!pending) {
          onCancel();
        }
      }}
    >
      <h2 id={titleId}>{title}</h2>
      <p>{message}</p>
      <div className="confirm__actions">
        <button type="button" onClick={onCancel} disabled={pending}>
          キャンセル
        </button>
        <button
          type="button"
          className="button--danger"
          onClick={onConfirm}
          disabled={pending}
        >
          {pending ? "処理中…" : confirmLabel}
        </button>
      </div>
    </dialog>
  );
}
