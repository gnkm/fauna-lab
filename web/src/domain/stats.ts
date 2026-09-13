import { SPLIT_IDS, type SplitId, SYSTEM_CLASSES } from "./classes";

export type ActiveModel = {
  ref: string;
  version: number;
  builtin: boolean;
};

export type Stats = {
  image_count: number;
  labeled_count: number;
  unlabeled_count: number;
  suggestion_count: number;
  per_class: Record<string, number>;
  per_split: Record<string, number>;
  active_model_ref: string | null;
  active_model: ActiveModel | null;
  baseline_registered: boolean;
  has_active_job: boolean;
};

export const EMPTY_STATS: Stats = {
  image_count: 0,
  labeled_count: 0,
  unlabeled_count: 0,
  suggestion_count: 0,
  per_class: Object.fromEntries(
    SYSTEM_CLASSES.map((item) => [item.classId, 0]),
  ),
  per_split: Object.fromEntries(SPLIT_IDS.map((id) => [id, 0])),
  active_model_ref: null,
  active_model: null,
  baseline_registered: false,
  has_active_job: false,
};

export function countForClass(stats: Stats, classId: string): number {
  const value = stats.per_class[classId];
  return typeof value === "number" ? value : 0;
}

export function countForSplit(stats: Stats, split: SplitId): number {
  const value = stats.per_split[split];
  return typeof value === "number" ? value : 0;
}
