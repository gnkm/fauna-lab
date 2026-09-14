import { type ClassId, SYSTEM_CLASSES } from "./classes";

export type ClassMetric = {
  precision: number;
  recall: number;
  f1: number;
  support: number;
};

export type ConfusionMatrix = {
  labels: ClassId[];
  matrix: number[][];
};

export type ModelMetrics = {
  accuracy: number;
  per_class: Record<ClassId, ClassMetric>;
  confusion_matrix: ConfusionMatrix;
};

export type ModelVersion = {
  ref: string;
  version: number;
  builtin: boolean;
  active: boolean;
  created_at: string;
  metrics: ModelMetrics | null;
};

export const CLASS_IDS: readonly ClassId[] = SYSTEM_CLASSES.map(
  (item) => item.classId,
);
