import { APIRequestContext, Page, expect } from '@playwright/test'
import crypto from 'node:crypto'

const SECRET = process.env.RM_JWT_SECRET || 'dev-only-jwt-signing-key-not-for-production-use'
const b64 = (v: object | Buffer) => (Buffer.isBuffer(v) ? v : Buffer.from(JSON.stringify(v))).toString('base64url')

/** Same HS256 token format the services use; for submitting test records as a client. */
export function token(sub: string, role: string) {
  const now = Math.floor(Date.now() / 1000)
  const head = b64({ alg: 'HS256', typ: 'JWT' })
  const body = b64({ sub, role, iss: 'reviewmesh', iat: now, exp: now + 600 })
  const sig = crypto.createHmac('sha256', SECRET).update(`${head}.${body}`).digest()
  return `${head}.${body}.${b64(sig)}`
}

export async function submit(request: APIRequestContext, title: string, docType = 'invoice', fields: Record<string, string> = { amount: '640.00', vendor: 'Fabrikam' }) {
  const r = await request.post('http://127.0.0.1:8890/v1/records', {
    headers: { Authorization: `Bearer ${token('acme-portal', 'submitter')}`, 'Idempotency-Key': `e2e-${crypto.randomUUID()}` },
    data: { title, doc_type: docType, filename: 'e2e.pdf', document_b64: Buffer.from(`%PDF-1.4\n% ${title}\n`).toString('base64'), fields },
  })
  expect(r.status()).toBe(201)
  return (await r.json()).record_id as string
}

export async function loginAs(page: Page, user: string) {
  await page.goto('/login')
  await page.locator('input[name=username]').fill(user)
  await page.locator('input[name=password]').fill(`${user}-demo`)
  await page.getByRole('button', { name: '登录' }).click()
  await expect(page.getByTestId('who')).toBeVisible()
}
