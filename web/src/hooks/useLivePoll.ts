import { useCallback, useEffect, useRef } from "react";

const isAbortError = (error: unknown): boolean =>
  error instanceof DOMException
    ? error.name === "AbortError"
    : error instanceof Error && error.name === "AbortError";

/**
 * 新しい要求を始めたら、完了が遅い古い要求の結果は捨てる。
 */
export function useLatestRequest(): () => { isCurrent: () => boolean } {
  const seq = useRef(0);
  return useCallback(() => {
    const token = ++seq.current;
    return { isCurrent: () => token === seq.current };
  }, []);
}

/**
 * 間隔ポーリング。前回の tick が残っていれば abort してから次を始める。
 * アンマウント時も in-flight を abort する。
 */
export function useLivePoll(
  enabled: boolean,
  intervalMs: number,
  onTick: (signal: AbortSignal) => Promise<void>,
  onError?: (error: unknown) => void,
): void {
  const onTickRef = useRef(onTick);
  const onErrorRef = useRef(onError);
  onTickRef.current = onTick;
  onErrorRef.current = onError;

  useEffect(() => {
    if (!enabled) {
      return;
    }
    let controller: AbortController | null = null;
    let cancelled = false;

    const tick = () => {
      controller?.abort();
      const next = new AbortController();
      controller = next;
      void onTickRef.current(next.signal).catch((error: unknown) => {
        if (cancelled || next.signal.aborted || isAbortError(error)) {
          return;
        }
        onErrorRef.current?.(error);
      });
    };

    const id = window.setInterval(tick, intervalMs);
    return () => {
      cancelled = true;
      window.clearInterval(id);
      controller?.abort();
    };
  }, [enabled, intervalMs]);
}
