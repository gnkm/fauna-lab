import { useEffect, useState } from "react";
import { errorMessage } from "../api/http";
import { fetchImages, uploadImages } from "../api/images";
import { BusyIndicator } from "../components/BusyIndicator";
import { Dropzone } from "../components/Dropzone";
import { EmptyState } from "../components/EmptyState";
import { ErrorBanner } from "../components/ErrorBanner";
import { FilterBar } from "../components/FilterBar";
import { ThumbnailCard } from "../components/ThumbnailCard";
import {
  EMPTY_FILTERS,
  type ImageFilters,
  type ImageItem,
  type UploadItem,
} from "../domain/images";
import { Link } from "../router/Link";
import { useRouter } from "../router/Router";

const PAGE_SIZE = 200;

export function ImagesPage() {
  const { navigate } = useRouter();
  const [filters, setFilters] = useState<ImageFilters>(EMPTY_FILTERS);
  const [images, setImages] = useState<ImageItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [results, setResults] = useState<UploadItem[]>([]);

  const pending = loading || uploading;

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    fetchImages(filters, PAGE_SIZE, 0, controller.signal)
      .then((page) => {
        setImages(page.items);
        setTotal(page.total);
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

  const onFiles = (files: File[]) => {
    if (pending) {
      return;
    }
    if (files.length > 50) {
      setError("1 回の操作で受け取れるファイルは 50 件までです。");
      return;
    }
    setUploading(true);
    setError(null);
    uploadImages(files)
      .then((items) => {
        setResults(items);
        const failed = items.filter((item) => !item.ok);
        if (failed.length > 0 && items.every((item) => !item.ok)) {
          setError(
            failed
              .map((item) => `${item.filename}: ${item.detail ?? "失敗"}`)
              .join(" "),
          );
        }
        return fetchImages(filters, PAGE_SIZE, 0);
      })
      .then((page) => {
        if (page !== undefined) {
          setImages(page.items);
          setTotal(page.total);
        }
      })
      .catch((reason: unknown) => {
        setError(errorMessage(reason));
      })
      .finally(() => {
        setUploading(false);
      });
  };

  const loadMore = () => {
    if (pending || images.length >= total) {
      return;
    }
    setLoading(true);
    fetchImages(filters, PAGE_SIZE, images.length)
      .then((page) => {
        setImages((current) => [...current, ...page.items]);
        setTotal(page.total);
      })
      .catch((reason: unknown) => {
        setError(errorMessage(reason));
      })
      .finally(() => {
        setLoading(false);
      });
  };

  const empty = !loading && images.length === 0 && total === 0;

  return (
    <article className="page page--wide" data-testid="images-page">
      <h1>画像</h1>
      <p className="lede">
        JPEG / PNG
        を登録し、サムネイルから詳細へ進めます。失敗はファイルごとに理由を出します。
      </p>
      {error !== null ? (
        <ErrorBanner message={error} onDismiss={() => setError(null)} />
      ) : null}
      <BusyIndicator
        pending={pending}
        label={uploading ? "画像を登録しています" : "画像を読み込み中です"}
      />

      <section aria-labelledby="upload-heading">
        <h2 id="upload-heading">アップロード</h2>
        <Dropzone disabled={pending} onFiles={onFiles} />
        {results.length > 0 ? (
          <ul className="upload-results" data-testid="upload-results">
            {results.map((item, index) => (
              <li
                key={`${item.filename}-${String(index)}`}
                className={item.ok ? "upload-ok" : "upload-fail"}
                data-ok={item.ok ? "true" : "false"}
              >
                {item.ok
                  ? `${item.filename}: 登録しました`
                  : `${item.filename}: ${item.detail ?? "失敗"}`}
              </li>
            ))}
          </ul>
        ) : null}
      </section>

      <section aria-labelledby="list-heading">
        <h2 id="list-heading">一覧</h2>
        <FilterBar
          filters={filters}
          onChange={setFilters}
          disabled={uploading}
        />
        {empty ? (
          <EmptyState title="登録された画像はまだありません">
            <p>
              上からファイルを選ぶか、ドラッグアンドドロップで投入してください。手元に画像が無いときは
              <Link to="/">概況</Link>
              の「サンプルデータを投入」から始められます。
            </p>
          </EmptyState>
        ) : (
          <>
            <p className="muted" data-testid="image-total">
              {String(images.length)} / {String(total)} 件
            </p>
            <div className="thumb-grid">
              {images.map((image) => (
                <ThumbnailCard
                  key={image.ref}
                  image={image}
                  onOpen={() => navigate(`/images/${image.ref}`)}
                />
              ))}
            </div>
            {images.length < total ? (
              <p>
                <button type="button" onClick={loadMore} disabled={pending}>
                  さらに読み込む
                </button>
              </p>
            ) : null}
          </>
        )}
      </section>
    </article>
  );
}
