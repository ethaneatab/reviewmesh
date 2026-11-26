import { expect, test } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'

const ROOT = path.resolve(import.meta.dirname, '..')
const REPO = JSON.parse(fs.readFileSync(path.join(ROOT, 'project.json'), 'utf8')).repo_url as string
const ORDER = ['submit', 's3', 'lambda', 'sqs', 'partition', 'validate', 'route', 'claim', 'audit', 'export']

/** The link must be REPO/blob/<sha>/<path>#Lx-Ly, and those lines must exist in the local file. */
function checkSourceHref(href: string) {
  const m = new RegExp(`^${REPO.replace(/[.*+?^${}()|[\]\\/]/g, '\\$&')}/blob/([0-9a-f]{40})/(.+)#L(\\d+)-L(\\d+)$`).exec(href)
  expect(m, href).not.toBeNull()
  const [, , file, a, b] = m!
  const lines = fs.readFileSync(path.join(ROOT, file), 'utf8').split('\n')
  expect(Number(a)).toBeGreaterThan(1)
  expect(Number(b)).toBeGreaterThanOrEqual(Number(a))
  expect(Number(b)).toBeLessThan(lines.length)
  expect(lines[Number(a) - 2]).toContain('@learn:')
  expect(lines[Number(b)]).toContain('@learn:end')
}

test('main line lights every stage in order from real backend state', async ({ page }) => {
  await page.goto('/learn')
  await page.getByTestId('learn-submit').click()
  await expect(page.getByTestId('learn-record')).toHaveText(/^rec_/)
  const doneAt: Record<string, number> = {}
  const waitDone = async (id: string, timeout = 30_000) => {
    await expect(page.getByTestId(`stage-${id}`)).toHaveAttribute('data-status', 'done', { timeout })
    doneAt[id] = Date.now()
  }
  for (const id of ORDER.slice(0, 7)) await waitDone(id)
  await expect(page.getByTestId('stage-claim')).toHaveAttribute('data-status', 'pending')
  await page.getByTestId('learn-claim').click()
  await waitDone('claim')
  await page.getByTestId('learn-approve').click()
  await waitDone('audit')
  await waitDone('export')
  // real data next to each stage
  await expect(page.getByTestId('kv-submit')).toContainText('HTTP 200，replay=true')
  await expect(page.getByTestId('kv-partition')).toContainText(/→ w[1-4]/)
  await page.getByTestId('open-partition').click()
  await expect(page.getByTestId('data-partition')).toContainText('"vnode"')
  await page.getByTestId('open-export').click()
  await expect(page.getByTestId('data-export')).toContainText('exports/decisions/')
  await expect(page.getByTestId('data-export')).toContainText('APPROVED')
  // source links: format + the lines really exist
  for (const id of ORDER) checkSourceHref((await page.getByTestId(`src-${id}`).getAttribute('href'))!)
  // the video slot degrades gracefully
  await page.getByTestId('video-submit').getByRole('button').click()
  // the committed video plays; before the videos were generated the slot said so instead
  const slot = page.getByTestId('video-submit')
  await expect(slot.locator('video').or(slot.getByTestId('video-pending'))).toBeVisible()
})

test('scale-out branch shows the moved keys', async ({ page }) => {
  await page.goto('/learn/scale')
  if (await page.getByTestId('branch-scale-in').isEnabled()) await page.getByTestId('branch-scale-in').click()
  await page.getByTestId('branch-scale-out').click()
  await expect(page.getByTestId('branch-scale-result')).toBeVisible()
  const pct = parseFloat(await page.getByTestId('branch-fraction').innerText())
  expect(pct).toBeGreaterThan(15)
  expect(pct).toBeLessThan(35)
  checkSourceHref((await page.getByTestId('branch-src-ring').getAttribute('href'))!)
  await page.getByTestId('branch-scale-in').click()
})

test('rollout branch rolls back automatically', async ({ page }) => {
  await page.goto('/learn/rollout')
  // The buttons fire their requests without waiting for each other, so wait for
  // each answer before the next click: on a slow CI runner a reset that was
  // answered after start/advance put the rollout back to 0%.
  for (const step of ['reset', 'start', 'advance']) {
    await Promise.all([page.waitForResponse((r) => r.url().includes(`/v1/rollout/${step}`)), page.getByTestId(`branch-${step}`).click()])
  }
  await expect(page.getByTestId('branch-percent')).toHaveText('10%')
  await page.getByTestId('branch-traffic').click()
  await expect.poll(async () => Number(await page.getByTestId('branch-samples').innerText()), { timeout: 15_000 }).toBeGreaterThan(5)
  await page.getByTestId('branch-fault').click()
  await expect(page.getByTestId('branch-rollout-status')).toHaveText('ROLLED_BACK', { timeout: 12_000 })
  await expect(page.getByTestId('branch-rollback-reason')).toContainText('v2 error rate')
  await page.getByTestId('branch-reset').click()
})

test('migration branch shows the contracted schema', async ({ page }) => {
  await page.goto('/learn/migration')
  await expect(page.getByTestId('migr-phase')).toHaveText('NEW_ONLY')
  await expect(page.getByTestId('migr-columns')).toContainText('reviewer_id')
  await expect(page.getByTestId('migr-history')).toContainText('V3')
})

test('interview tab: open a question and read its answer', async ({ page }) => {
  await page.goto('/learn/interview')
  const q = page.getByTestId('q-0-0')
  await q.locator('summary').click()
  await expect(q.getByTestId('answer')).toBeVisible()
  await expect(q.getByTestId('answer')).not.toBeEmpty()
})

test('problems tab: expand one problem', async ({ page }) => {
  await page.goto('/learn/problems')
  const first = page.locator('[data-testid^="problem-q"]').first()
  await first.locator('summary').click()
  await expect(first.getByTestId(/section-0$/).first()).toBeVisible()
  await first.getByRole('button', { name: '看讲解视频' }).click()
  await expect(first.locator('video').or(first.getByTestId('video-pending'))).toBeVisible()
})
