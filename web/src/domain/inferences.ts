import type { ClassId } from "./classes";

export type ClassScore = {
  class_id: ClassId;
  confidence: number;
};

export type Inference = {
  ref: string;
  image_ref: string;
  model_ref: string;
  top_class_id: ClassId;
  top_confidence: number;
  other_mass: number | null;
  low_confidence: boolean;
  created_at: string;
  scores: ClassScore[];
};

export const MAX_INFERENCE_IMAGES = 20;

export function topScores(inference: Inference, count = 3): ClassScore[] {
  return inference.scores.slice(0, count);
}
