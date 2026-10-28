// Example — one test() per TC, title starts with the TC id, tags = TC id + priority + basis ids (+ stage).
import { test, expect } from '@playwright/test';
import { shot, watchPage } from '../../lib/evidence';

test('TC-W-001 owner sees 3 evidence thumbnails', { tag: ['@TC-W-001', '@P0', '@AC-1', '@S1'] }, async ({ page }, info) => {
  const watch = watchPage(page);
  await page.goto('/');
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  await shot(page, info, 'home');
  watch.assertClean();
});
