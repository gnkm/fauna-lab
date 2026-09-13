export type NavItem = {
  to: string;
  label: string;
};

export const NAV_ITEMS: readonly NavItem[] = [
  { to: "/", label: "概況" },
  { to: "/images", label: "画像" },
  { to: "/annotate", label: "アノテーション" },
  { to: "/splits", label: "分割" },
  { to: "/train", label: "学習" },
  { to: "/models", label: "モデル" },
  { to: "/infer", label: "推論" },
];
