import path from "node:path";
import { type APIRequestContext, expect } from "@playwright/test";

export const FIXTURE_DIR = path.resolve("assets/fixtures/images");

export const FIXTURE_JPEG_A = path.join(FIXTURE_DIR, "samoyed_151.jpg");
export const FIXTURE_JPEG_B = path.join(FIXTURE_DIR, "chihuahua_173.jpg");

export const PNG_RED = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
  "base64",
);

export async function clearImages(request: APIRequestContext): Promise<void> {
  for (;;) {
    const response = await request.get("/api/images?limit=200");
    expect(response.ok()).toBeTruthy();
    const body = (await response.json()) as { items: { ref: string }[] };
    if (body.items.length === 0) {
      return;
    }
    for (const item of body.items) {
      const deleted = await request.delete(`/api/images/${item.ref}`);
      expect(deleted.status()).toBe(204);
    }
  }
}
