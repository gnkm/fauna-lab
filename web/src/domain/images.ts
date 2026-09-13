import {
  type ClassId,
  SPLIT_IDS,
  type SplitId,
  SYSTEM_CLASSES,
} from "./classes";

export type { ClassId, SplitId };

export type LabelSource = "human" | "model_suggested";

export type ConfirmedLabel = {
  class_id: ClassId;
  source: LabelSource;
};

export type Suggestion = {
  class_id: ClassId;
  confidence: number;
  model_ref: string;
};

export type ImageItem = {
  ref: string;
  sha256: string;
  split: SplitId;
  label: ConfirmedLabel | null;
  suggestion: Suggestion | null;
  original_name: string;
  size_bytes: number;
  width: number;
  height: number;
  created_at: string;
  media_type: string;
};

export type ImageFilters = {
  labeled: "all" | "yes" | "no";
  classId: ClassId | "";
  split: SplitId | "";
};

export const EMPTY_FILTERS: ImageFilters = {
  labeled: "all",
  classId: "",
  split: "",
};

export type UploadItem = {
  filename: string;
  ok: boolean;
  ref?: string;
  code?: string;
  detail?: string;
};

const CLASS_IDS = new Set<string>(SYSTEM_CLASSES.map((item) => item.classId));
const SPLIT_SET = new Set<string>(SPLIT_IDS);

export function isClassId(value: string): value is ClassId {
  return CLASS_IDS.has(value);
}

export function isSplitId(value: string): value is SplitId {
  return SPLIT_SET.has(value);
}

export function thumbnailUrl(ref: string): string {
  return `/api/images/${encodeURIComponent(ref)}/thumbnail`;
}

export function withLabel(
  image: ImageItem,
  label: ConfirmedLabel | null,
): ImageItem {
  return {
    ...image,
    label,
    suggestion: label === null ? image.suggestion : null,
    split: label === null ? "unassigned" : image.split,
  };
}
