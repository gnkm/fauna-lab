import { useCallback, useEffect, useMemo, useState } from "react";
import { errorMessage } from "../api/http";
import { fetchImages } from "../api/images";
import { bulkPutLabels, deleteImageLabel, putImageLabel } from "../api/labels";
import { BusyIndicator } from "../components/BusyIndicator";
import { ClassSelect } from "../components/ClassSelect";
import { EmptyState } from "../components/EmptyState";
import { ErrorBanner } from "../components/ErrorBanner";
import { FilterBar } from "../components/FilterBar";
import { ThumbnailCard } from "../components/ThumbnailCard";
import { SYSTEM_CLASSES } from "../domain/classes";
import {
  type ClassId,
  EMPTY_FILTERS,
  type ImageFilters,
  type ImageItem,
  withLabel,
} from "../domain/images";
import { Link } from "../router/Link";
import { useRouter } from "../router/Router";

const PAGE_SIZE = 200;

export function AnnotatePage() {
  const { navigate } = useRouter();
  const [filters, setFilters] = useState<ImageFilters>({
    ...EMPTY_FILTERS,
    labeled: "no",
  });
  const [images, setImages] = useState<ImageItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [focusIndex, setFocusIndex] = useState(0);
  const [classId, setClassId] = useState<ClassId | "">("");
  const [notice, setNotice] = useState<string | null>(null);

  const busy = loading || pending;

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    fetchImages(filters, PAGE_SIZE, 0, controller.signal)
      .then((page) => {
        setImages(page.items);
        setTotal(page.total);
        setSelected(new Set());
        setFocusIndex(0);
        setError(null);
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted) {
          return;
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
  }, [filters]);

  const focused = images[focusIndex] ?? null;
  const selectedRefs = useMemo(() => Array.from(selected), [selected]);

  const applyLocal = useCallback(
    (refs: string[], label: ImageItem["label"]) => {
      const refSet = new Set(refs);
      setImages((current) =>
        current.map((item) =>
          refSet.has(item.ref) ? withLabel(item, label) : item,
        ),
      );
    },
    [],
  );

  const onAssignOne = useCallback(
    (ref: string, nextClass: ClassId) => {
      if (pending) {
        return;
      }
      setPending(true);
      putImageLabel(ref, nextClass)
        .then((label) => {
          applyLocal([ref], label);
          setNotice("確定ラベルを付けました。");
          setError(null);
        })
        .catch((reason: unknown) => {
          setError(errorMessage(reason));
        })
        .finally(() => {
          setPending(false);
        });
    },
    [applyLocal, pending],
  );

  const onBulk = () => {
    if (pending || classId === "" || selectedRefs.length === 0) {
      return;
    }
    setPending(true);
    bulkPutLabels(selectedRefs, classId)
      .then((count) => {
        applyLocal(selectedRefs, { class_id: classId, source: "human" });
        setNotice(`確定ラベルを ${String(count)} 件付けました。`);
        setSelected(new Set());
        setError(null);
      })
      .catch((reason: unknown) => {
        setError(errorMessage(reason));
      })
      .finally(() => {
        setPending(false);
      });
  };

  const onClearSelected = () => {
    if (pending || selectedRefs.length === 0) {
      return;
    }
    setPending(true);
    Promise.all(selectedRefs.map((ref) => deleteImageLabel(ref)))
      .then(() => {
        applyLocal(selectedRefs, null);
        setNotice("選択したラベルを解除しました。");
        setSelected(new Set());
        setError(null);
      })
      .catch((reason: unknown) => {
        setError(errorMessage(reason));
      })
      .finally(() => {
        setPending(false);
      });
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
    const index = images.findIndex((item) => item.ref === ref);
    if (index >= 0) {
      setFocusIndex(index);
    }
  };

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target;
      if (
        target instanceof HTMLElement &&
        (target.tagName === "INPUT" ||
          target.tagName === "SELECT" ||
          target.tagName === "TEXTAREA" ||
          target.isContentEditable)
      ) {
        return;
      }
      if (images.length === 0 || pending) {
        return;
      }
      if (event.key === "ArrowRight") {
        event.preventDefault();
        setFocusIndex((index) => Math.min(images.length - 1, index + 1));
        return;
      }
      if (event.key === "ArrowLeft") {
        event.preventDefault();
        setFocusIndex((index) => Math.max(0, index - 1));
        return;
      }
      const digit = Number(event.key);
      if (digit >= 1 && digit <= 8) {
        const spec = SYSTEM_CLASSES.find((item) => item.displayOrder === digit);
        const current = images[focusIndex];
        if (spec !== undefined && current !== undefined) {
          event.preventDefault();
          onAssignOne(current.ref, spec.classId);
        }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
    };
  }, [images, focusIndex, pending, onAssignOne]);

  const empty = !loading && images.length === 0;

  return (
    <article className="page page--wide" data-testid="annotate-page">
      <h1>アノテーション</h1>
      <p className="lede">
        サムネイルに確定ラベルを付けます。確定と候補は色の違うバッジで区別します。付与後は再読み込みせずに表示を更新します。
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
        label={pending ? "ラベルを更新しています" : "画像を読み込み中です"}
      />

      <FilterBar filters={filters} onChange={setFilters} disabled={pending} />

      <section aria-labelledby="assign-heading">
        <h2 id="assign-heading">付与</h2>
        <div className="form-row">
          <ClassSelect
            value={classId}
            onChange={setClassId}
            disabled={pending}
          />
          <button
            type="button"
            onClick={() => {
              if (focused !== null && classId !== "") {
                onAssignOne(focused.ref, classId);
              }
            }}
            disabled={pending || classId === "" || focused === null}
            data-testid="assign-one"
          >
            フォーカス中の 1 枚に付与
          </button>
          <button
            type="button"
            onClick={onBulk}
            disabled={pending || classId === "" || selectedRefs.length === 0}
            data-testid="assign-bulk"
          >
            選択へ一括付与（{String(selectedRefs.length)}）
          </button>
          <button
            type="button"
            onClick={onClearSelected}
            disabled={pending || selectedRefs.length === 0}
          >
            選択のラベルを解除
          </button>
        </div>
        <p className="muted">
          キーボード: 左右で画像を移動、数字 1〜8 でクラスを付与します。
        </p>
      </section>

      <section aria-labelledby="suggest-heading">
        <h2 id="suggest-heading">候補ラベル</h2>
        <p data-testid="suggestion-unavailable">
          候補の生成・採用・却下・閾値一括採用は、候補 API
          がまだ接続されていないためこの画面では操作できません。有効モデルができたあとに
          <Link to="/">概況</Link>
          から案内します。確定ラベルと分割はこの画面と
          <Link to="/splits">分割</Link>
          で進められます。
        </p>
      </section>

      {empty ? (
        <EmptyState title="ラベルを付ける画像がありません">
          <p>
            先に<Link to="/images">画像</Link>を登録するか、
            <Link to="/">概況</Link>
            からサンプルを投入してください。絞り込みを「すべて」にすると、既にラベルがある画像も表示します。
          </p>
        </EmptyState>
      ) : (
        <div className="thumb-grid">
          {images.map((image, index) => (
            <ThumbnailCard
              key={image.ref}
              image={image}
              selected={selected.has(image.ref)}
              focused={index === focusIndex}
              onToggle={() => toggle(image.ref)}
              onOpen={() => navigate(`/images/${image.ref}`)}
            />
          ))}
        </div>
      )}
      {images.length < total ? (
        <p className="muted">先頭 {String(PAGE_SIZE)} 件を表示しています。</p>
      ) : null}
    </article>
  );
}
