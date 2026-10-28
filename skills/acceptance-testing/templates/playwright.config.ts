// .qa/playwright.config.ts — shared by every test run in this repo. Select a run with env:
//   QA_SLUG=<slug> QA_RUN=<run-id> npx playwright test [--grep @TC-W-001]
import { defineConfig } from '@playwright/test';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import YAML from 'yaml';

const QA = __dirname;
const slug = process.env.QA_SLUG;
if (!slug) throw new Error('QA_SLUG=<slug> is required');
const run = process.env.QA_RUN ?? 'dev';
const profile = YAML.parse(readFileSync(path.join(QA, 'profile.yml'), 'utf8')) ?? {};
const runDir = path.join(QA, slug, 'runs', run);
const viewports: Record<string, any> = profile.viewports ?? { desktop: { width: 1280, height: 800 } };

export default defineConfig({
  testDir: path.join(QA, slug, 'tests'),
  outputDir: path.join(runDir, 'artifacts'),
  timeout: profile.run?.timeout_ms ?? 60_000,
  expect: { timeout: 10_000 },
  workers: profile.run?.workers ?? 1,
  fullyParallel: false,
  retries: 0, // flakiness is measured with --repeat-each, never hidden by retries
  reporter: [['list'], ['json', { outputFile: path.join(runDir, 'pw.json') }]],
  use: {
    baseURL: profile.surfaces?.web?.base_url,
    headless: profile.browser?.headless ?? true,
    locale: profile.browser?.locale,
    timezoneId: profile.browser?.timezone,
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  projects: Object.entries(viewports).map(([name, v]) => ({
    name,
    use: {
      viewport: { width: v.width, height: v.height },
      isMobile: !!v.isMobile,
      hasTouch: !!v.isMobile,
      deviceScaleFactor: v.dpr ?? 1,
    },
  })),
});
