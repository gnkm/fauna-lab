export type PageId =
  | "overview"
  | "images"
  | "image-detail"
  | "annotate"
  | "splits"
  | "train"
  | "train-job"
  | "models"
  | "infer"
  | "not-found";

export type Match = {
  id: PageId;
  path: string;
  params: Record<string, string>;
};

export function normalizePath(pathname: string): string {
  if (pathname === "" || pathname === "/") {
    return "/";
  }
  return pathname.replace(/\/+$/, "") || "/";
}

export function matchPath(pathname: string): Match {
  const path = normalizePath(pathname);
  if (path === "/") {
    return { id: "overview", path, params: {} };
  }
  if (path === "/images") {
    return { id: "images", path, params: {} };
  }
  const image = /^\/images\/([^/]+)$/.exec(path);
  if (image?.[1]) {
    return { id: "image-detail", path, params: { ref: image[1] } };
  }
  if (path === "/annotate") {
    return { id: "annotate", path, params: {} };
  }
  if (path === "/splits") {
    return { id: "splits", path, params: {} };
  }
  if (path === "/train") {
    return { id: "train", path, params: {} };
  }
  const job = /^\/train\/([^/]+)$/.exec(path);
  if (job?.[1]) {
    return { id: "train-job", path, params: { ref: job[1] } };
  }
  if (path === "/models") {
    return { id: "models", path, params: {} };
  }
  if (path === "/infer") {
    return { id: "infer", path, params: {} };
  }
  return { id: "not-found", path, params: {} };
}

export const PAGE_TITLES: Record<PageId, string> = {
  overview: "概況",
  images: "画像",
  "image-detail": "画像の詳細",
  annotate: "アノテーション",
  splits: "分割",
  train: "学習",
  "train-job": "学習ジョブ",
  models: "モデル",
  infer: "推論",
  "not-found": "画面が見つかりません",
};
