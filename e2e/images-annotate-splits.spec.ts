import fs from "node:fs";
import { expect, test } from "@playwright/test";
import {
  clearImages,
  FIXTURE_JPEG_A,
  FIXTURE_JPEG_B,
  PNG_RED,
} from "./helpers";

test.beforeEach(async ({ request }) => {
  await clearImages(request);
});

test("複数ファイルを上げ、一部失敗しても他は登録される", async ({ page }) => {
  await page.goto("/images");
  await expect(
    page.getByRole("heading", { name: "登録された画像はまだありません" }),
  ).toBeVisible();

  await page.getByTestId("upload-input").setInputFiles([
    {
      name: "samoyed.jpg",
      mimeType: "image/jpeg",
      buffer: fs.readFileSync(FIXTURE_JPEG_A),
    },
    {
      name: "chihuahua.jpg",
      mimeType: "image/jpeg",
      buffer: fs.readFileSync(FIXTURE_JPEG_B),
    },
    {
      name: "fake.png",
      mimeType: "text/plain",
      buffer: Buffer.from("this is not an image"),
    },
  ]);

  const results = page.getByTestId("upload-results");
  await expect(results.getByText("登録しました")).toHaveCount(2);
  await expect(results.getByText("fake.png")).toContainText(
    "JPEG または PNG として解釈できません",
  );
  await expect(page.getByTestId("image-total")).toHaveText("2 / 2 件");
});

test("ファイル名のタグは画面上で解釈されない", async ({ page }) => {
  await page.goto("/images");
  await page.getByTestId("upload-input").setInputFiles([
    {
      name: "<img src=x onerror=alert(1)>.png",
      mimeType: "image/png",
      buffer: PNG_RED,
    },
  ]);
  await expect(page.getByTestId("upload-results")).toContainText(
    "<img src=x onerror=alert(1)>.png: 登録しました",
  );
  await expect(page.locator("img[src='x']")).toHaveCount(0);
  await expect(
    page.getByText("<img src=x onerror=alert(1)>.png", { exact: true }),
  ).toBeVisible();
});

test("アップロードからラベルと分割まで UI で完了し _state に反映される", async ({
  page,
  request,
}) => {
  await page.goto("/images");
  await page
    .getByTestId("upload-input")
    .setInputFiles([FIXTURE_JPEG_A, FIXTURE_JPEG_B]);
  await expect(page.getByTestId("image-total")).toHaveText("2 / 2 件");

  await page
    .getByRole("navigation", { name: "メイン" })
    .getByRole("link", { name: "アノテーション", exact: true })
    .click();
  await expect(page).toHaveURL("/annotate");
  await expect(
    page.getByRole("heading", { name: "アノテーション", level: 1 }),
  ).toBeVisible();
  await expect(page.getByTestId("suggestion-unavailable")).toBeVisible();

  const cards = page.locator(".thumb-card");
  await expect(cards).toHaveCount(2);
  await expect(cards.getByText("未ラベル")).toHaveCount(2);

  await cards.nth(0).getByRole("checkbox").check();
  await page.getByTestId("class-select").selectOption("samoyed");
  await page.getByTestId("assign-one").click();
  await expect(page.getByText("確定ラベルを付けました。")).toBeVisible();
  await expect(cards).toHaveCount(1);

  await cards.nth(0).getByRole("checkbox").check();
  await page.getByTestId("class-select").selectOption("chihuahua");
  await page.getByTestId("assign-bulk").click();
  await expect(page.getByText("確定ラベルを 1 件付けました。")).toBeVisible();
  await expect(cards).toHaveCount(0);

  await page.getByTestId("filter-labeled").selectOption("all");
  await expect(cards).toHaveCount(2);
  await expect(page.getByText("確定: サモエド")).toBeVisible();
  await expect(page.getByText("確定: チワワ")).toBeVisible();

  await page
    .getByRole("navigation", { name: "メイン" })
    .getByRole("link", { name: "分割", exact: true })
    .click();
  await expect(page).toHaveURL("/splits");
  await expect(page.getByTestId("split-labeled-count")).toHaveText("2");
  await page.getByTestId("split-run").click();
  await expect(page.getByTestId("split-notice")).toContainText(
    "確定ラベル 2 件を分割しました",
  );
  await expect(page.getByTestId("split-count-unassigned")).toHaveText("0");

  await page
    .getByRole("navigation", { name: "メイン" })
    .getByRole("link", { name: "概況", exact: true })
    .click();
  await expect(page.getByTestId("stat-image-count")).toHaveText("2");
  await expect(page.getByRole("rowheader", { name: "サモエド" })).toBeVisible();

  const stateResponse = await request.get("/api/_state");
  expect(stateResponse.ok()).toBeTruthy();
  const state = (await stateResponse.json()) as {
    images: Array<{
      label: { class_id: string } | null;
      split: string;
    }>;
  };
  expect(state.images).toHaveLength(2);
  const classIds = state.images.map((image) => image.label?.class_id).sort();
  expect(classIds).toEqual(["chihuahua", "samoyed"]);
  expect(state.images.every((image) => image.split !== "unassigned")).toBe(
    true,
  );
});

test("分割の比率 1/0/0 は送信前に拒否する", async ({ page, request }) => {
  await page.goto("/images");
  await page.getByTestId("upload-input").setInputFiles([FIXTURE_JPEG_A]);
  await expect(page.getByTestId("image-total")).toHaveText("1 / 1 件");
  await page
    .getByRole("navigation", { name: "メイン" })
    .getByRole("link", { name: "アノテーション", exact: true })
    .click();
  await page.getByTestId("class-select").selectOption("samoyed");
  await page.getByTestId("assign-one").click();
  await expect(page.getByText("確定ラベルを付けました。")).toBeVisible();

  await page
    .getByRole("navigation", { name: "メイン" })
    .getByRole("link", { name: "分割", exact: true })
    .click();
  await page.getByTestId("split-train").fill("1");
  await page.getByTestId("split-val").fill("0");
  await page.getByTestId("split-test").fill("0");
  const trainValid = await page
    .getByTestId("split-train")
    .evaluate((element: HTMLInputElement) => element.validity.valid);
  expect(trainValid).toBe(false);
  await page.getByTestId("split-run").click();
  await expect(page.getByTestId("split-notice")).toHaveCount(0);
  const stats = (await (await request.get("/api/stats")).json()) as {
    per_split: { unassigned: number };
  };
  expect(stats.per_split.unassigned).toBe(1);
});

test("ラベル保存後の一覧再取得失敗でも保存成功を残し再同期できる", async ({
  page,
}) => {
  await page.goto("/images");
  await page
    .getByTestId("upload-input")
    .setInputFiles([FIXTURE_JPEG_A, FIXTURE_JPEG_B]);
  await expect(page.getByTestId("image-total")).toHaveText("2 / 2 件");

  let failImageList = false;
  await page.route("**/api/images*", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const isListGet =
      request.method() === "GET" &&
      (url.pathname === "/api/images" || url.pathname === "/api/images/");
    if (isListGet && failImageList) {
      await route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({
          code: "internal_error",
          detail: "simulated list failure",
        }),
      });
      return;
    }
    await route.continue();
  });
  await page.route(/\/api\/images\/[^/]+\/label$/, async (route) => {
    if (route.request().method() === "PUT") {
      const response = await route.fetch();
      failImageList = true;
      await route.fulfill({ response });
      return;
    }
    await route.continue();
  });
  await page.route("**/api/labels/bulk", async (route) => {
    const response = await route.fetch();
    failImageList = true;
    await route.fulfill({ response });
  });

  await page.goto("/annotate");
  const cards = page.locator(".thumb-card");
  await expect(cards).toHaveCount(2);

  await page.getByTestId("class-select").selectOption("samoyed");
  await page.getByTestId("assign-one").click();
  await expect(page.getByText("確定ラベルを付けました。")).toBeVisible();
  await expect(page.getByRole("alert")).toContainText(
    "保存は完了しましたが、一覧の再読み込みに失敗しました。",
  );
  await expect(page.getByTestId("retry-reload")).toBeVisible();
  await expect(cards).toHaveCount(1);

  failImageList = false;
  await page.getByTestId("retry-reload").click();
  await expect(page.getByRole("alert")).toHaveCount(0);
  await expect(page.getByTestId("retry-reload")).toHaveCount(0);
  await expect(cards).toHaveCount(1);

  await cards.nth(0).getByRole("checkbox").check();
  await page.getByTestId("class-select").selectOption("chihuahua");
  await page.getByTestId("assign-bulk").click();
  await expect(page.getByText("確定ラベルを 1 件付けました。")).toBeVisible();
  await expect(page.getByRole("alert")).toContainText(
    "保存は完了しましたが、一覧の再読み込みに失敗しました。",
  );
  await expect(page.getByTestId("retry-reload")).toBeVisible();
  await expect(cards).toHaveCount(0);
});

test("画像削除は確認ダイアログを出し、キャンセルできる", async ({ page }) => {
  await page.goto("/images");
  await page.getByTestId("upload-input").setInputFiles([FIXTURE_JPEG_A]);
  await expect(page.getByTestId("image-total")).toHaveText("1 / 1 件");
  await page.locator(".thumb-card__image").click();
  await expect(
    page.getByRole("heading", { name: "画像の詳細", level: 1 }),
  ).toBeVisible();
  await page.getByRole("button", { name: "この画像を削除" }).click();
  await expect(
    page.getByRole("heading", { name: "この画像を削除しますか？" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "キャンセル" }).click();
  await expect(
    page.getByRole("heading", { name: "この画像を削除しますか？" }),
  ).toHaveCount(0);
  await expect(page).toHaveURL(/\/images\//);
  await page.getByRole("button", { name: "この画像を削除" }).click();
  await page.getByRole("button", { name: "削除する" }).click();
  await expect(page).toHaveURL("/images");
  await expect(
    page.getByRole("heading", { name: "登録された画像はまだありません" }),
  ).toBeVisible();
});
