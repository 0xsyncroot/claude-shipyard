// .qa/lib/evidence.ts — evidence helpers shared by every spec.
import { expect, type Page, type TestInfo } from '@playwright/test';

/** Full-page screenshot attached to the test result; collect maps it to the TC's evidence. */
export async function shot(page: Page, info: TestInfo, label: string, fullPage = true) {
  const file = info.outputPath(`${label.replace(/[^\w.-]+/g, '-')}.png`);
  await page.screenshot({ path: file, fullPage });
  await info.attach(label, { path: file, contentType: 'image/png' });
}

/** Records console errors, page errors and HTTP >= 500 responses for the "console:" expected line. */
export function watchPage(page: Page, ignore: RegExp[] = []) {
  const problems: string[] = [];
  const keep = (s: string) => !ignore.some((r) => r.test(s)) && problems.push(s);
  page.on('console', (m) => m.type() === 'error' && keep(`console: ${m.text()}`));
  page.on('pageerror', (e) => keep(`pageerror: ${e.message}`));
  page.on('response', (r) => r.status() >= 500 && keep(`http ${r.status()}: ${r.request().method()} ${r.url()}`));
  return {
    problems,
    assertClean: () => expect.soft(problems, 'console errors / 5xx').toEqual([]),
  };
}
