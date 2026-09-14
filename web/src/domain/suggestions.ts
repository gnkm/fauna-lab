import type { ClassId } from "./classes";

export type SuggestionItem = {
  image_ref: string;
  class_id: ClassId;
  confidence: number;
  model_ref: string;
};

export type SuggestionOrder = "asc" | "desc";

export type SuggestionCreateResult = {
  generated_count: number;
  skipped_labeled_count: number;
};
