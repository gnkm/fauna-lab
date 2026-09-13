export type ClassId =
  | "samoyed"
  | "great_pyrenees"
  | "boxer"
  | "american_bulldog"
  | "chihuahua"
  | "miniature_pinscher"
  | "pomeranian"
  | "havanese";

export type SplitId = "train" | "val" | "test" | "unassigned";

export type ClassSpec = {
  classId: ClassId;
  displayName: string;
  displayOrder: number;
};

/** SRS 3.5.2。表示は日本語名（REQ-USE-006）。 */
export const SYSTEM_CLASSES: readonly ClassSpec[] = [
  { classId: "samoyed", displayName: "サモエド", displayOrder: 1 },
  {
    classId: "great_pyrenees",
    displayName: "グレート・ピレニーズ",
    displayOrder: 2,
  },
  { classId: "boxer", displayName: "ボクサー", displayOrder: 3 },
  {
    classId: "american_bulldog",
    displayName: "アメリカン・ブルドッグ",
    displayOrder: 4,
  },
  { classId: "chihuahua", displayName: "チワワ", displayOrder: 5 },
  {
    classId: "miniature_pinscher",
    displayName: "ミニチュア・ピンシャー",
    displayOrder: 6,
  },
  { classId: "pomeranian", displayName: "ポメラニアン", displayOrder: 7 },
  { classId: "havanese", displayName: "ハバニーズ", displayOrder: 8 },
];

export const SPLIT_LABELS: Record<SplitId, string> = {
  train: "訓練",
  val: "検証",
  test: "試験",
  unassigned: "未割当",
};

export const SPLIT_IDS: readonly SplitId[] = [
  "train",
  "val",
  "test",
  "unassigned",
];

export function displayNameFor(classId: string): string {
  const found = SYSTEM_CLASSES.find((item) => item.classId === classId);
  return found?.displayName ?? classId;
}
