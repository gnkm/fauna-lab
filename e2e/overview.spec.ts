import { expect, test } from "@playwright/test";
import { clearImages } from "./helpers";

const NAV_ITEMS = [
  { label: "概況", url: "/" },
  { label: "画像", url: "/images" },
  { label: "アノテーション", url: "/annotate" },
  { label: "分割", url: "/splits" },
  { label: "学習", url: "/train" },
  { label: "モデル", url: "/models" },
  { label: "推論", url: "/infer" },
] as const;

test.beforeEach(async ({ request }) => {
  await clearImages(request);
});

test("概況に URL 直達し、リロード後も同じ画面", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL("/");
  await expect(page.getByTestId("overview-page")).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "概況", level: 1 }),
  ).toBeVisible();
  await page.reload();
  await expect(page).toHaveURL("/");
  await expect(
    page.getByRole("heading", { name: "概況", level: 1 }),
  ).toBeVisible();
});

test("空状態の案内と日本語クラス名がある", async ({ page }) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "データがまだありません" }),
  ).toBeVisible();
  await expect(page.getByText("次の順で進めると")).toBeVisible();
  await expect(page.getByRole("rowheader", { name: "サモエド" })).toBeVisible();
  await expect(
    page.getByRole("rowheader", { name: "ハバニーズ" }),
  ).toBeVisible();
  await expect(page.getByTestId("stat-image-count")).toHaveText("0");
  await expect(page.getByTestId("active-model-missing")).toBeVisible();
});

test("ナビから全機能へ到達でき、直達とリロードで画面が保たれる", async ({
  page,
}) => {
  await page.goto("/");
  const nav = page.getByRole("navigation", { name: "メイン" });
  for (const item of NAV_ITEMS) {
    await expect(
      nav.getByRole("link", { name: item.label, exact: true }),
    ).toBeVisible();
  }

  for (const item of NAV_ITEMS) {
    await page.goto(item.url);
    await expect(page).toHaveURL(item.url);
    await expect(
      page.getByRole("heading", { name: item.label, level: 1 }),
    ).toBeVisible();
    await page.reload();
    await expect(page).toHaveURL(item.url);
    await expect(
      page.getByRole("heading", { name: item.label, level: 1 }),
    ).toBeVisible();
    await expect(page.getByText("準備中")).toHaveCount(0);
  }
});
