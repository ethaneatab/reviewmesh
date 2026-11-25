import { expect, test } from '@playwright/test'
import { loginAs, submit } from './helpers'

test('a submitted invoice reaches the finance queue, gets approved and exported', async ({ page, request }) => {
  const title = `E2E invoice ${Date.now()}`
  const rid = await submit(request, title)
  await loginAs(page, 'rita')
  await page.getByTestId('queue-finance').click()
  const row = page.getByTestId(`task-${rid}`)
  await expect(row).toBeVisible({ timeout: 30_000 })
  await row.getByTestId('claim').click()
  page.on('dialog', (d) => d.accept('totals match the purchase order'))
  await page.getByTestId('status-filter').selectOption('CLAIMED')
  await row.getByTestId('approve').click()
  await page.getByTestId('status-filter').selectOption('APPROVED')
  await expect(row).toBeVisible()
  await row.getByRole('link', { name: title }).click()
  await expect(page.getByTestId('tl-EXPORTED')).toBeVisible({ timeout: 30_000 })
  await page.getByTestId('tl-toggle-EXPORTED').click()
  await expect(page.getByTestId('tl-json-EXPORTED')).toContainText(`exports/decisions/`)
  await expect(page.getByTestId('tl-json-EXPORTED')).toContainText('APPROVED')
  for (const s of ['SUBMITTED', 'LAMBDA_SEEN', 'PARTITIONED', 'VALIDATED', 'HANDED_OFF', 'CLAIMED', 'APPROVED']) {
    await expect(page.getByTestId(`tl-${s}`).first()).toBeVisible()
  }
})

test('two reviewers: only the one who claimed can decide', async ({ browser, request }) => {
  const rid = await submit(request, `E2E race ${Date.now()}`, 'claim', { claim_number: 'CL-88' })
  const a = await (await browser.newContext()).newPage()
  const b = await (await browser.newContext()).newPage()
  await loginAs(a, 'rita')
  await loginAs(b, 'sam')
  for (const p of [a, b]) await p.getByTestId('queue-claims').click()
  await expect(a.getByTestId(`task-${rid}`)).toBeVisible({ timeout: 30_000 })
  await a.getByTestId(`task-${rid}`).getByTestId('claim').click()
  await expect(a.getByTestId(`task-${rid}`)).toHaveCount(0)              // it left the OPEN list
  await b.getByTestId('status-filter').selectOption('CLAIMED')
  await expect(b.getByTestId(`task-${rid}`)).toBeVisible()
  await expect(b.getByTestId(`task-${rid}`).getByTestId('approve')).toHaveCount(0)
})

test('ring page scales out and shows only keys moving to w4', async ({ page }) => {
  await page.goto('/ring')
  await expect(page.getByTestId('ring-svg')).toBeVisible()
  if (await page.getByTestId('scale-in').isEnabled()) await page.getByTestId('scale-in').click()
  await page.getByTestId('scale-out').click()
  await expect(page.getByTestId('scale-result')).toBeVisible()
  const frac = parseFloat((await page.getByTestId('moved-fraction').innerText()).replace('%', ''))
  expect(frac).toBeGreaterThan(15)
  expect(frac).toBeLessThan(35)
  await expect(page.getByTestId('scale-result')).toContainText('→w4')
  await expect(page.getByTestId('scale-result')).not.toContainText('→w1')
  await page.getByTestId('scale-in').click()
  await expect(page.getByTestId('member-w4')).toContainText('待命')
})
