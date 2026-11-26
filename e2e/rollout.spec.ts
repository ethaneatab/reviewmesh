import { expect, test } from '@playwright/test'

test('release console: ramp, inject a fault, watch the automatic rollback', async ({ page }) => {
  await page.goto('/rollout')
  await page.getByTestId('rollout-reset').click()
  await expect(page.getByTestId('rollout-status')).toHaveText('IDLE')
  await page.getByTestId('rollout-start').click()
  await page.getByTestId('rollout-advance').click()
  await expect(page.getByTestId('rollout-percent')).toHaveText('10%')
  await page.getByTestId('rollout-traffic').click()
  await expect.poll(async () => Number(await page.getByTestId('window-samples').innerText()), { timeout: 15_000 }).toBeGreaterThan(5)
  await page.getByTestId('rollout-fault').click()
  await expect(page.getByTestId('rollout-status')).toHaveText('ROLLED_BACK', { timeout: 12_000 })
  await expect(page.getByTestId('rollout-percent')).toHaveText('0%')
  await expect(page.getByTestId('rollback-reason')).toContainText('v2 error rate')
  await page.getByTestId('rollout-reset').click()
})
