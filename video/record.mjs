#!/usr/bin/env node
// Screen-record the learn page, paced by video/narration.json.
//
// For each segment: run its action, put a red frame around its `highlight` element, then hold for the
// segment's spoken length (video/durations.json {id: seconds}; 4 s when the file is missing).
// Writes video/out/learn.webm and video/timeline.json {segments: [{id, part, startMs, durMs, rect}]},
// where startMs is measured from the start of the recording, so audio can be laid on top later.
//
//   node video/record.mjs                 needs scripts/demo.sh running and no tests in flight
//   RM_UI_URL=http://127.0.0.1:5189 NARRATION=video/narration.json node video/record.mjs
import { chromium } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const BASE = process.env.RM_UI_URL || 'http://127.0.0.1:5189'
const segments = JSON.parse(fs.readFileSync(process.env.NARRATION || path.join(HERE, 'narration.json'), 'utf8'))
const durPath = path.join(HERE, 'durations.json')
const durations = fs.existsSync(durPath) ? JSON.parse(fs.readFileSync(durPath, 'utf8')) : {}
const OUT = path.join(HERE, 'out')
fs.mkdirSync(OUT, { recursive: true })

const VIEW = { width: 1600, height: 900 }
const browser = await chromium.launch()
const context = await browser.newContext({ viewport: VIEW, deviceScaleFactor: 1, recordVideo: { dir: OUT, size: VIEW } })
const page = await context.newPage()
const t0 = Date.now()
let runPath = '/learn'

const RING_CSS = `
@keyframes rm-pop { 0% { transform: scale(1.25); opacity: 0 } 60% { transform: scale(.97); opacity: 1 } 100% { transform: scale(1) } }
#rm-ring { position: fixed; z-index: 99998; pointer-events: none; border: 3px solid #e5383b;
  box-shadow: 0 0 0 6px rgba(229,56,59,.25); animation: rm-pop .5s ease-out; }
#rm-caption { position: fixed; z-index: 99999; left: 50%; bottom: 22px; transform: translateX(-50%); max-width: 88%;
  background: #1b1f3b; color: #fef3c7; font: 14px ui-monospace, Menlo, monospace; padding: 8px 14px; border-radius: 8px; word-break: break-all; }`

/** Draw the red frame around the first visible match; returns the target and frame rectangles. */
async function ring(selector, shape = 'box') {
  await page.evaluate(() => document.getElementById('rm-ring')?.remove())
  if (!selector) return null
  const loc = page.locator(selector).first()
  await loc.waitFor({ state: 'visible', timeout: 20_000 })
  await loc.scrollIntoViewIfNeeded()
  await page.waitForTimeout(150)
  await page.evaluate(({ selector, shape, css }) => {
    if (!document.getElementById('rm-ring-css')) {
      const st = document.createElement('style')
      st.id = 'rm-ring-css'
      st.textContent = css
      document.head.appendChild(st)
    }
    const el = Array.from(document.querySelectorAll(selector)).find((e) => e.getBoundingClientRect().width > 0)
    if (!el) throw new Error(`nothing visible matches ${selector}`)
    const box = document.createElement('div')
    box.id = 'rm-ring'
    document.body.appendChild(box)
    const place = () => {
      const r = el.getBoundingClientRect()
      const padX = shape === 'circle' ? Math.max(16, r.width * 0.25) : 6
      const padY = shape === 'circle' ? Math.max(12, r.height * 0.5) : 5
      box.style.left = `${r.left - padX}px`
      box.style.top = `${r.top - padY}px`
      box.style.width = `${r.width + 2 * padX}px`
      box.style.height = `${r.height + 2 * padY}px`
      box.style.borderRadius = shape === 'circle' ? '50%' : '9px'
    }
    place()
    const follow = () => { if (box.isConnected) { place(); requestAnimationFrame(follow) } }
    requestAnimationFrame(follow)
  }, { selector, shape, css: RING_CSS })
  await page.waitForTimeout(600) // let the pop animation settle before measuring
  return page.evaluate((selector) => {
    const el = Array.from(document.querySelectorAll(selector)).find((e) => e.getBoundingClientRect().width > 0)
    const box = document.getElementById('rm-ring')
    const r = el.getBoundingClientRect()
    const f = box.getBoundingClientRect()
    return { target: [r.left, r.top, r.width, r.height].map(Math.round), frame: [f.left, f.top, f.width, f.height].map(Math.round) }
  }, selector)
}

async function caption(text) {
  await page.evaluate(({ text, css }) => {
    if (!document.getElementById('rm-ring-css')) {
      const st = document.createElement('style')
      st.id = 'rm-ring-css'
      st.textContent = css
      document.head.appendChild(st)
    }
    let c = document.getElementById('rm-caption')
    if (!text) { c?.remove(); return }
    if (!c) { c = document.createElement('div'); c.id = 'rm-caption'; document.body.appendChild(c) }
    c.textContent = text
  }, { text, css: RING_CSS })
}

const byId = (id) => page.getByTestId(id)
const stageDone = (id, timeout = 60_000) => page.locator(`[data-testid=stage-${id}][data-status=done]`).waitFor({ timeout })

async function act(action) {
  const [name, ...rest] = action.split(':')
  const arg = rest.join(':')
  switch (name) {
    case 'goto':
      await page.goto(BASE + arg)
      await page.waitForLoadState('networkidle')
      return
    case 'submit':
      await byId('learn-submit').click()
      await byId('learn-record').waitFor()
      runPath = `/learn?run=${await byId('learn-record').innerText()}`
      await stageDone('submit')
      return
    case 'back_main':
      await page.goto(BASE + runPath)
      await stageDone('validate')
      return
    case 'wait_stage':
      return stageDone(arg)
    case 'open':
      await stageDone(arg)
      await byId(`open-${arg}`).click()
      return
    case 'show_src': {
      const id = arg.includes('-') ? arg : `src-${arg}`
      await caption(`看源码 → ${await byId(id).getAttribute('href')}`)
      return
    }
    case 'click':
      await byId(arg).click()
      await page.waitForTimeout(400)
      return
    case 'click_wait': {
      const [btn, stage] = arg.split(':')
      await byId(btn).click()
      return stageDone(stage)
    }
    case 'rollout_prepare':
      await page.goto(BASE + '/learn/rollout')
      await byId('branch-reset').waitFor()
      for (const b of ['branch-reset', 'branch-start', 'branch-advance', 'branch-traffic']) {
        await byId(b).click()
        await page.waitForTimeout(350)
      }
      await page.locator('[data-testid=branch-percent]', { hasText: '10%' }).waitFor()
      return
    case 'wait_samples':
      for (let i = 0; i < 60; i++) {
        if (Number(await byId('branch-samples').innerText()) > 5) return
        await page.waitForTimeout(250)
      }
      throw new Error('rollout traffic never produced samples')
    case 'click_rollback':
      await byId('branch-fault').click()
      await page.locator('[data-testid=branch-rollout-status]', { hasText: 'ROLLED_BACK' }).waitFor({ timeout: 20_000 })
      return
    case 'open_q':
      await page.locator('[data-testid=q-0-0] summary').click()
      return
    case 'open_problem':
      await page.goto(BASE + '/learn/problems')
      await page.locator('[data-testid=problem-q01-lambda-dist-info] summary').click()
      return
    case 'finish':
      await page.goto(BASE + runPath)
      await stageDone('export')
      await page.request.post(BASE + '/api/intake/v1/rollout/reset')
      return
    case 'noop':
      return
    default:
      throw new Error(`unknown action ${action}`)
  }
}

const timeline = []
for (const seg of segments) {
  const startMs = Date.now() - t0
  await caption('')
  await act(seg.action)
  const rect = await ring(seg.highlight, seg.shape || 'box')
  const holdMs = (durations[seg.id] ?? 4) * 1000
  const spent = Date.now() - t0 - startMs
  await page.waitForTimeout(Math.max(holdMs - spent, 800))
  timeline.push({ id: seg.id, part: seg.part, startMs, durMs: Date.now() - t0 - startMs, plannedMs: holdMs, highlight: seg.highlight, rect })
  console.log(`${seg.id} ${seg.part} @${(startMs / 1000).toFixed(1)}s ${seg.action}`)
}
await caption('')
const video = page.video()
await context.close()
await browser.close()
const webm = path.join(OUT, 'learn.webm')
fs.renameSync(await video.path(), webm)
fs.writeFileSync(path.join(HERE, 'timeline.json'), JSON.stringify({ video: 'video/out/learn.webm', segments: timeline }, null, 2) + '\n')
console.log(`wrote ${path.relative(process.cwd(), webm)} and video/timeline.json (${timeline.length} segments, ${((Date.now() - t0) / 1000).toFixed(0)} s)`)
