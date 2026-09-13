import { useEffect, useState } from "react";

export function useDelayedFlag(active: boolean, delayMs = 300): boolean {
  const [shown, setShown] = useState(false);

  useEffect(() => {
    if (!active) {
      setShown(false);
      return;
    }
    const id = window.setTimeout(() => {
      setShown(true);
    }, delayMs);
    return () => {
      window.clearTimeout(id);
    };
  }, [active, delayMs]);

  return shown;
}

export function BusyIndicator({
  pending,
  label = "処理中です",
}: {
  pending: boolean;
  label?: string;
}) {
  const shown = useDelayedFlag(pending);
  if (!shown) {
    return null;
  }
  return (
    <div className="busy" role="status" aria-live="polite">
      <span className="busy__spinner" aria-hidden="true" />
      <span>{label}</span>
    </div>
  );
}
