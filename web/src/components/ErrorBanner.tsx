export function ErrorBanner({
  message,
  onDismiss,
}: {
  message: string;
  onDismiss?: () => void;
}) {
  return (
    <div className="banner banner--error" role="alert">
      <p>{message}</p>
      {onDismiss !== undefined ? (
        <button type="button" className="banner__dismiss" onClick={onDismiss}>
          閉じる
        </button>
      ) : null}
    </div>
  );
}
