export type JobStatus =
  | "QUEUED"
  | "RUNNING"
  | "SUCCEEDED"
  | "FAILED"
  | "CANCELED";

export type Job = {
  ref: string;
  status: JobStatus;
  current_epoch: number;
  total_epochs: number;
  model_ref: string | null;
  failed: boolean;
};

export type JobLogEntry = {
  epoch: number;
  train_loss: number;
  val_loss: number;
  val_accuracy: number;
  duration_seconds: number;
};

export type JobCreateParams = {
  epochs: number;
  batch_size: number;
  learning_rate: number;
  seed: number;
  augmentation: boolean;
  use_baseline: boolean;
};

export const DEFAULT_JOB_PARAMS: JobCreateParams = {
  epochs: 10,
  batch_size: 32,
  learning_rate: 0.001,
  seed: 42,
  augmentation: true,
  use_baseline: true,
};

export const JOB_STATUS_LABEL: Record<JobStatus, string> = {
  QUEUED: "待機中",
  RUNNING: "実行中",
  SUCCEEDED: "成功",
  FAILED: "失敗",
  CANCELED: "中止",
};

const LIVE_STATUSES = new Set<JobStatus>(["QUEUED", "RUNNING"]);

export function isLiveJob(job: Job): boolean {
  return LIVE_STATUSES.has(job.status);
}

export function parseJobStatus(value: string): JobStatus {
  if (
    value === "QUEUED" ||
    value === "RUNNING" ||
    value === "SUCCEEDED" ||
    value === "FAILED" ||
    value === "CANCELED"
  ) {
    return value;
  }
  return "FAILED";
}
