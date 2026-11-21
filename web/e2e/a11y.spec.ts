import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

// Public pages a signed-out visitor (or the ArgosX scanner) can reach.
const PAGES = ["/", "/login"];
const TAGS = ["wcag2a", "wcag2aa", "best-practice"];

for (const path of PAGES) {
  test(`no axe violations on ${path}`, async ({ page }) => {
    await page.goto(path);
    await page.waitForLoadState("networkidle");
    const { violations } = await new AxeBuilder({ page }).withTags(TAGS).analyze();
    const summary = violations.map((v) => `${v.id} (${v.nodes.length}): ${v.nodes.slice(0, 3).map((n) => n.target.join(" ")).join(" | ")}`);
    expect(summary).toEqual([]);
  });
}
