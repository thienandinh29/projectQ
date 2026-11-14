import { expect, test, type Page } from "@playwright/test";
import { answerKeys } from "./keys";

// A learner the stack serves draft items to (DRAFT_ITEM_LEARNERS); CI creates it.
const LEARNER =
  process.env.E2E_LEARNER_ID ?? "00000000-0000-4000-8000-0000000e2e01";
const KEYS = answerKeys();

async function asLearner(page: Page, id: string | null) {
  await page.addInitScript((value) => {
    if (value) localStorage.setItem("nodetrail_english_learner", value);
    else localStorage.removeItem("nodetrail_english_learner");
  }, id);
}

async function currentItem(page: Page): Promise<string> {
  const id = await page.locator("[data-item-id]").getAttribute("data-item-id");
  if (!id) throw new Error("no question on the page");
  return id;
}

/** Chooses the right option, or a wrong one, from the item bank's key. */
async function answer(page: Page, right: boolean) {
  const id = await currentItem(page);
  const key = KEYS.get(id);
  expect(key, `answer key for ${id}`).toBeTruthy();
  const options = page.getByRole("radio");
  const texts = await options.allInnerTexts();
  const index = texts.findIndex(
    (t) => (t.split("\n").at(-1)?.trim() === key) === right,
  );
  await options.nth(index).click();
  await page.getByRole("button", { name: "Gửi" }).click();
}

test("the level test ends with an estimated level, never presented as a score", async ({
  page,
}) => {
  await asLearner(page, LEARNER);
  await page.goto("/kiem-tra");
  await page.getByRole("button", { name: "Bắt đầu" }).click();
  const result = page.getByText("Kết quả ước lượng");
  for (let i = 0; i < 40; i++) {
    await expect(page.locator("[data-item-id]").or(result)).toBeVisible();
    if (await result.isVisible()) break;
    const id = await currentItem(page);
    if (KEYS.has(id)) {
      // grammar: drafts are labelled
      await expect(page.getByText("Bản nháp", { exact: true })).toBeVisible();
      await answer(page, true);
    } else {
      await page.getByRole("radio").first().click(); // the vocabulary part
      await page.getByRole("button", { name: "Gửi" }).click();
    }
    // wait for a different question, or the result
    await expect(
      page.locator(`[data-item-id]:not([data-item-id="${id}"])`).or(result),
    ).toBeVisible();
  }
  await expect(result).toBeVisible();
  await expect(
    page.getByText("ước lượng, không phải điểm IELTS"),
  ).toBeVisible();
  await page.getByRole("link", { name: "Xem lộ trình của bạn" }).click();
  await expect(
    page.getByRole("heading", { name: "Lộ trình của bạn" }),
  ).toBeVisible();
});

test("a failed milestone test explains each mistake and opens quick checks", async ({
  page,
}) => {
  await asLearner(page, LEARNER);
  await page.goto("/on-tap/cot-moc/conditional-3");
  await page.getByRole("button", { name: "Bắt đầu" }).click();
  for (let i = 0; i < 3; i++) {
    await answer(page, false);
    await expect(page.getByText("Chưa đúng.")).toBeVisible();
    await expect(page.getByText("Đáp án đúng")).toBeVisible();
    if (i < 2)
      await page.getByRole("button", { name: "Câu tiếp theo" }).click();
  }
  await expect(page.getByText("Chưa qua cột mốc")).toBeVisible();
  await page.getByRole("button", { name: "Câu tiếp theo" }).click();
  await expect(page.getByText("Kiểm tra nhanh từng phần")).toBeVisible();
  for (
    let i = 0;
    i < 4 && (await page.locator("[data-item-id]").count());
    i++
  ) {
    await answer(page, false);
    const more = page.getByRole("button", { name: "Câu tiếp theo" });
    await expect(more.or(page.getByText("Nên luyện trước"))).toBeVisible();
    if (await more.isVisible()) await more.click();
    else break;
  }
  await expect(page.getByText("Nên luyện trước")).toBeVisible();
  await expect(page.getByRole("link", { name: "Luyện ngay" })).toBeVisible();
});

test("a new word is taught, asked, and scheduled", async ({ page }) => {
  await asLearner(page, null); // a fresh learner: vocabulary needs no draft permission
  await page.goto("/tu-vung");
  await expect(page.getByText("Từ mới", { exact: true })).toBeVisible();
  const lemma = (await page.locator(".en-word-top strong").innerText()).trim();
  await page.getByRole("button", { name: "Tôi đã đọc, hỏi tôi đi" }).click();
  const options = page.getByRole("radio");
  const texts = await options.allInnerTexts();
  await options
    .nth(texts.findIndex((t) => t.split("\n").at(-1)?.trim() === lemma))
    .click();
  await page.getByRole("button", { name: "Gửi" }).click();
  await expect(page.getByText("Đúng rồi.")).toBeVisible();
  await expect(page.getByText("Ôn lại vào")).toBeVisible();
});

test("an essay is written, measured by the worker, and deleted", async ({
  page,
}) => {
  await asLearner(page, LEARNER); // the starter prompts are drafts
  await page.goto("/viet");
  await expect(page.getByRole("heading", { name: "Luyện viết" })).toBeVisible();
  await page.locator('a[href="/viet/t2-plastic-ban"]').click();
  const essay =
    "Plastic bags is cheap. However, they pollute rivers.\n\nIn conclusion, a ban is sensible.";
  await page.getByRole("textbox").fill(essay);
  await expect(page.getByTestId("word-count")).toContainText("14 từ");
  await expect(page.getByTestId("word-count")).toContainText("cần ít nhất 250");
  const send = page.getByRole("button", { name: "Gửi bài" });
  await expect(send).toBeDisabled(); // the notice comes first
  await page.getByLabel("Tôi đã đọc và đồng ý").check();
  await send.click();
  await expect(page.getByRole("heading", { name: "Đã phân tích" })).toBeVisible(
    {
      timeout: 30_000,
    },
  );
  const result = page.getByTestId("essay-result");
  await expect(result).toContainText("14 / 250");
  await expect(result).toContainText("không phải điểm IELTS");
  await expect(result).toContainText("Đối lập");
  await expect(result).toContainText("Kết luận");
  if (process.env.LANGUAGETOOL_URL) {
    // the grammar check (specs/writing/step-2.2.md): this learner may see the draft error map
    const grammar = page.getByTestId("essay-grammar");
    await expect(
      grammar.locator('[data-errant-type="R:VERB:SVA"]'),
    ).toContainText("are");
    await expect(
      grammar.getByRole("link", { name: /Đã ghi vào lộ trình/ }),
    ).toBeVisible();
    // hint first: the learner fixes the sentence themselves (step 2.4)
    await grammar.getByRole("button", { name: "Tự sửa câu này" }).click();
    await page.getByLabel("Câu bạn sửa").fill("Plastic bags are cheap.");
    await page.getByRole("button", { name: "Kiểm tra" }).click();
    await expect(
      page.getByText("Đúng rồi! Bạn đã tự sửa được lỗi này."),
    ).toBeVisible();
  }
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Xóa bài viết" }).click();
  await expect(page.getByRole("heading", { name: "Luyện viết" })).toBeVisible();
});
