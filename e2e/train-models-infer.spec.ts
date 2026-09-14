import { expect, test } from "@playwright/test";
import { clearImages, FIXTURE_JPEG_A } from "./helpers";

// VER-UI-001: 学習・モデル・推論・候補の画面。実行中ジョブの自動更新。

const JOB_REF = "11111111-1111-4111-8111-111111111111";
const MODEL0 = "00000000-0000-4000-8000-000000000000";
const MODEL1 = "11111111-1111-4111-8111-111111111111";
const IMAGE_REF = "22222222-2222-4222-8222-222222222222";
const INFER_REF = "33333333-3333-4333-8333-333333333333";

const CLASS_IDS = [
  "samoyed",
  "great_pyrenees",
  "boxer",
  "american_bulldog",
  "chihuahua",
  "miniature_pinscher",
  "pomeranian",
  "havanese",
] as const;

function emptyMetrics() {
  const zero = {
    precision: 0.5,
    recall: 0.5,
    f1: 0.5,
    support: 1,
  };
  const per_class = Object.fromEntries(
    CLASS_IDS.map((id) => [id, { ...zero }]),
  );
  per_class.samoyed = { precision: 1, recall: 1, f1: 1, support: 1 };
  const matrix = CLASS_IDS.map((row) =>
    CLASS_IDS.map((col) => (row === col && row === "samoyed" ? 1 : 0)),
  );
  return {
    accuracy: 0.875,
    per_class,
    confusion_matrix: { labels: [...CLASS_IDS], matrix },
  };
}

test.beforeEach(async ({ request }) => {
  await clearImages(request);
});

test("学習フォームは既定値を出し、空でも準備中と書かない", async ({ page }) => {
  await page.goto("/train");
  await expect(page.getByTestId("train-page")).toBeVisible();
  await expect(page.getByTestId("train-epochs")).toHaveValue("10");
  await expect(page.getByTestId("train-batch")).toHaveValue("32");
  await expect(page.getByTestId("train-lr")).toHaveValue("0.001");
  await expect(page.getByTestId("train-lr")).toHaveAttribute("min", "0.0001");
  await page.getByTestId("train-lr").fill("0");
  await expect
    .poll(async () =>
      page
        .getByTestId("train-lr")
        .evaluate((el) => (el as HTMLInputElement).validity.rangeUnderflow),
    )
    .toBe(true);
  await page.getByTestId("train-lr").fill("0.001");
  await expect(page.getByTestId("train-seed")).toHaveValue("42");
  await expect(page.getByTestId("train-aug")).toBeChecked();
  await expect(page.getByTestId("train-baseline")).toBeChecked();
  await expect(page.getByText("準備中")).toHaveCount(0);
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "学習", level: 1 }),
  ).toBeVisible();
});

test("実行中ジョブは手動再読み込みなしに 5 秒以上で進捗が更新される", async ({
  page,
}) => {
  test.setTimeout(30_000);
  let epoch = 0;
  await page.route(/\/api\/jobs/, async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (request.method() === "GET" && url.pathname === "/api/jobs") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          items: [
            {
              ref: JOB_REF,
              status: "RUNNING",
              current_epoch: epoch,
              total_epochs: 10,
              model_ref: null,
              failed: false,
            },
          ],
          total: 1,
        }),
      });
      return;
    }
    if (
      request.method() === "GET" &&
      url.pathname === `/api/jobs/${JOB_REF}/logs`
    ) {
      const items =
        epoch < 1
          ? []
          : [
              {
                epoch: 1,
                train_loss: 0.4321,
                val_loss: 0.4,
                val_accuracy: 0.8,
                duration_seconds: 1.2,
              },
            ];
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ items, total: items.length }),
      });
      return;
    }
    await route.continue();
  });

  await page.goto("/train");
  await expect(page.getByTestId(`job-status-${JOB_REF}`)).toHaveText("実行中");
  await expect(page.getByTestId(`job-epoch-${JOB_REF}`)).toHaveText("0 / 10");
  const started = Date.now();
  await page.waitForTimeout(2500);
  epoch = 1;
  await expect(page.getByTestId(`job-epoch-${JOB_REF}`)).toHaveText("1 / 10", {
    timeout: 10_000,
  });
  await expect(page.getByTestId(`job-val-acc-${JOB_REF}`)).toHaveText("80.0%");
  await expect(page.getByTestId(`job-loss-${JOB_REF}`)).toHaveText("0.4321");
  const elapsed = Date.now() - started;
  if (elapsed < 5000) {
    await page.waitForTimeout(5000 - elapsed);
  }
  expect(Date.now() - started).toBeGreaterThanOrEqual(5000);
  await expect(page).toHaveURL("/train");
  await expect(page.getByTestId(`job-status-${JOB_REF}`)).toHaveText("実行中");
});

test("学習中止は確認ダイアログを出し、キャンセルできる", async ({ page }) => {
  await page.route(/\/api\/jobs/, async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (request.method() === "GET" && url.pathname === "/api/jobs") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          items: [
            {
              ref: JOB_REF,
              status: "QUEUED",
              current_epoch: 0,
              total_epochs: 10,
              model_ref: null,
              failed: false,
            },
          ],
          total: 1,
        }),
      });
      return;
    }
    await route.continue();
  });
  await page.goto("/train");
  await page.getByTestId(`job-cancel-${JOB_REF}`).click();
  await expect(
    page.getByRole("heading", { name: "この学習ジョブを中止しますか？" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "キャンセル" }).click();
  await expect(
    page.getByRole("heading", { name: "この学習ジョブを中止しますか？" }),
  ).toHaveCount(0);
  await expect(page.getByTestId(`job-status-${JOB_REF}`)).toHaveText("待機中");
});

test("モデル一覧は版 0 を内蔵と示し削除 UI を出さない", async ({ page }) => {
  const metrics = emptyMetrics();
  await page.route(/\/api\/models/, async (route) => {
    const url = new URL(route.request().url());
    if (route.request().method() === "GET" && url.pathname === "/api/models") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          items: [
            {
              ref: MODEL1,
              version: 1,
              builtin: false,
              active: false,
              created_at: "2026-09-14T00:00:00Z",
              metrics,
            },
            {
              ref: MODEL0,
              version: 0,
              builtin: true,
              active: true,
              created_at: "2026-09-13T00:00:00Z",
              metrics: null,
            },
          ],
          total: 2,
        }),
      });
      return;
    }
    await route.continue();
  });
  await page.goto("/models");
  await expect(page.getByText("版 0（内蔵）")).toBeVisible();
  await expect(page.getByTestId(`model-delete-${MODEL0}`)).toHaveCount(0);
  await expect(page.getByTestId(`model-delete-${MODEL1}`)).toBeVisible();
  await page.getByRole("button", { name: "版 1" }).click();
  await expect(page.getByTestId("model-accuracy")).toContainText("87.5%");
  await expect(page.getByTestId("confusion-matrix")).toBeVisible();
  await expect(page.getByTestId("confusion-matrix")).toContainText(
    "正解＼予測",
  );
  await expect(page.getByTestId("per-class-metrics")).toContainText("サモエド");
});

test("有効モデルが無い推論は利用者へ提示する", async ({ page }) => {
  await page.goto("/infer");
  await expect(page.getByTestId("infer-no-model")).toBeVisible();
  await expect(page.getByTestId("infer-no-model")).toContainText(
    "有効モデルがありません",
  );
  await expect(page.getByText("準備中")).toHaveCount(0);
});

test("推論結果は最上位と上位 3 を百分率・小数 1 位で示す", async ({ page }) => {
  const scores = CLASS_IDS.map((class_id, index) => ({
    class_id,
    confidence: Math.max(0, 0.9 - index * 0.1),
  }));
  await page.route("**/api/stats", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        image_count: 0,
        labeled_count: 0,
        unlabeled_count: 0,
        suggestion_count: 0,
        per_class: {},
        per_split: {},
        active_model_ref: MODEL0,
        active_model: { ref: MODEL0, version: 0, builtin: true },
        baseline_registered: true,
        has_active_job: false,
      }),
    });
  });
  await page.route("**/api/images**", async (route) => {
    const url = new URL(route.request().url());
    if (route.request().method() === "GET" && url.pathname === "/api/images") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ items: [], total: 0 }),
      });
      return;
    }
    await route.continue();
  });
  await page.route(/\/api\/inferences/, async (route) => {
    const method = route.request().method();
    if (method === "GET") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ items: [], total: 0 }),
      });
      return;
    }
    if (method === "POST") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          items: [
            {
              ref: INFER_REF,
              image_ref: IMAGE_REF,
              model_ref: MODEL0,
              top_class_id: "samoyed",
              top_confidence: 0.901,
              other_mass: 0.1,
              low_confidence: false,
              created_at: "2026-09-14T00:00:00Z",
              scores,
            },
          ],
        }),
      });
      return;
    }
    await route.continue();
  });
  await page.goto("/infer");
  await expect(page.getByTestId("infer-active-model")).toContainText(
    "ベースライン",
  );
  await page.getByTestId("upload-input").setInputFiles([FIXTURE_JPEG_A]);
  await expect(page.getByTestId("infer-results")).toContainText("サモエド");
  await expect(page.getByTestId("infer-results")).toContainText("90.1%");
  await expect(page.getByTestId("infer-results")).toContainText("1位 サモエド");
  await expect(page.getByTestId("infer-results")).toContainText("2位");
  await expect(page.getByTestId("infer-results")).toContainText("3位");
});

test("候補は生成・採用・却下・閾値一括と昇順既定がある", async ({ page }) => {
  let items: Array<{
    image_ref: string;
    class_id: string;
    confidence: number;
    model_ref: string;
  }> = [
    {
      image_ref: IMAGE_REF,
      class_id: "chihuahua",
      confidence: 0.21,
      model_ref: MODEL0,
    },
  ];
  await page.route(/\/api\/suggestions/, async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (request.method() === "GET" && url.pathname === "/api/suggestions") {
      expect(url.searchParams.get("order") ?? "desc").toBe("asc");
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ items, total: items.length }),
      });
      return;
    }
    if (request.method() === "POST" && url.pathname === "/api/suggestions") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ generated_count: 1, skipped_labeled_count: 0 }),
      });
      return;
    }
    if (url.pathname === "/api/suggestions/accept") {
      items = [];
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ updated_count: 1 }),
      });
      return;
    }
    if (url.pathname === "/api/suggestions/reject") {
      items = [];
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ updated_count: 1 }),
      });
      return;
    }
    if (url.pathname === "/api/suggestions/accept-by-threshold") {
      const body = request.postDataJSON() as { min_confidence: number };
      expect(body.min_confidence).toBeCloseTo(0.8);
      items = [];
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ updated_count: 1 }),
      });
      return;
    }
    await route.continue();
  });
  await page.goto("/annotate");
  await expect(page.getByTestId("suggest-order")).toHaveValue("asc");
  await expect(page.getByTestId("suggest-list")).toContainText("21.0%");
  await page.getByTestId("suggest-generate").click();
  await expect(page.getByText("候補を 1 件生成しました")).toBeVisible();
  await expect(page.getByTestId("suggest-accept-threshold")).toBeEnabled();
  await page.getByTestId("suggest-accept-threshold").click();
  await expect(
    page.getByText("信頼度 80% 以上の候補を 1 件採用"),
  ).toBeVisible();
});

test("概況から学習・推論までドキュメント無しで辿れる", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("次の順で進めると")).toBeVisible();
  await expect(
    page.getByRole("link", { name: "アノテーション" }).first(),
  ).toBeVisible();
  await page.getByRole("link", { name: "学習", exact: true }).first().click();
  await expect(page).toHaveURL("/train");
  await expect(page.getByTestId("train-start")).toBeVisible();
  await page
    .getByRole("navigation", { name: "メイン" })
    .getByRole("link", { name: "推論", exact: true })
    .click();
  await expect(page).toHaveURL("/infer");
  await expect(
    page.getByRole("heading", { name: "推論", level: 1 }),
  ).toBeVisible();
  await expect(page.getByText("準備中")).toHaveCount(0);
});
