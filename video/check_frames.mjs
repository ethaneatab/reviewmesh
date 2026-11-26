#!/usr/bin/env node
// After a recording: (1) every red frame really encloses its target and the target has a size;
// (2) cut one PNG per chosen segment from the webm so a person can look at the frame placement.
//   node video/check_frames.mjs [s02 s12 s21 s34]
import { execFileSync } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const tl = JSON.parse(fs.readFileSync(path.join(HERE, 'timeline.json'), 'utf8'))
let bad = 0
for (const s of tl.segments) {
  if (!s.rect) continue
  const [tx, ty, tw, th] = s.rect.target
  const [fx, fy, fw, fh] = s.rect.frame
  const ok = tw > 0 && th > 0 && fx <= tx && fy <= ty && fx + fw >= tx + tw && fy + fh >= ty + th && fw < tw + 400 && fh < th + 300
  const onScreen = ty >= 0 && ty + th <= 900 && tx >= 0 && tx + tw <= 1600
  if (!ok || !onScreen) { bad++; console.log(`OFF ${s.id} target=${s.rect.target} frame=${s.rect.frame}`) }
}
console.log(`${tl.segments.length - bad}/${tl.segments.length} frames on target`)
const pick = process.argv.slice(2).length ? process.argv.slice(2) : ['s02', 's12', 's21', 's34']
const outDir = path.join(HERE, 'out', 'frames')
fs.mkdirSync(outDir, { recursive: true })
for (const id of pick) {
  const s = tl.segments.find((x) => x.id === id)
  if (!s) continue
  const at = (s.startMs + s.durMs - 500) / 1000
  const png = path.join(outDir, `${id}.png`)
  execFileSync('ffmpeg', ['-v', 'error', '-y', '-ss', at.toFixed(2), '-i', path.join(HERE, 'out', 'learn.webm'), '-frames:v', '1', png])
  console.log(`frame ${id} @${at.toFixed(1)}s -> ${path.relative(process.cwd(), png)}`)
}
process.exit(bad ? 1 : 0)
