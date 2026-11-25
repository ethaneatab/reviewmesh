import { useCallback, useEffect, useState } from 'react'
import { intake } from '../api'

type RingData = {
  epoch: number
  kind: string
  vnodes: number
  live: string[]
  members: Record<string, { active: boolean; alive: boolean; port: number }>
  points: { node: string; vnode: number; angle: number }[]
  counts: Record<string, number>
  keys: { key: string; angle: number; owner: string; vnode: string }[]
  history: { epoch: number; before: string[]; after: string[]; reason: string; at: number }[]
}
type ScaleResult = {
  keys_checked: number
  moved: number
  moved_fraction: number
  expected_fraction: number
  moved_keys: { key: string; from: string; to: string }[]
}

const COLORS: Record<string, string> = { w1: 'var(--w1)', w2: 'var(--w2)', w3: 'var(--w3)', w4: 'var(--w4)' }
const R = 170
const C = 200

function xy(angle: number, r: number) {
  const t = (angle * Math.PI) / 180
  return [C + r * Math.sin(t), C - r * Math.cos(t)]
}

export function RingPicture({ data, moved, testid }: { data: RingData; moved?: Set<string>; testid?: string }) {
  return (
    <svg viewBox="0 0 400 400" width="100%" style={{ maxWidth: 420 }} data-testid={testid} role="img" aria-label="hash ring">
      <circle cx={C} cy={C} r={R} fill="none" stroke="var(--line)" strokeWidth={2} />
      {data.points.map((p, i) => {
        const [x1, y1] = xy(p.angle, R - 6)
        const [x2, y2] = xy(p.angle, R + 8)
        return <line key={i} x1={x1} y1={y1} x2={x2} y2={y2} stroke={COLORS[p.node] ?? '#888'} strokeWidth={1.4} />
      })}
      {data.keys.map((k) => {
        const isMoved = moved?.has(k.key)
        const [x, y] = xy(k.angle, isMoved ? R - 30 : R - 18)
        return <circle key={k.key} cx={x} cy={y} r={isMoved ? 3.4 : 2.2} fill={COLORS[k.owner] ?? '#888'} opacity={moved && !isMoved ? 0.35 : 0.9} />
      })}
      <text x={C} y={C - 6} textAnchor="middle" fontSize={15} fontWeight={700} fill="var(--ink)">epoch {data.epoch}</text>
      <text x={C} y={C + 14} textAnchor="middle" fontSize={12} fill="var(--muted)">{data.kind} · {data.vnodes} vnodes / worker</text>
    </svg>
  )
}

export default function Ring() {
  const [data, setData] = useState<RingData | null>(null)
  const [result, setResult] = useState<ScaleResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const load = useCallback(() => intake<RingData>('/v1/ring?sample=600').then(setData).catch((e) => setErr(e.message)), [])
  useEffect(() => { load() }, [load])

  async function scale(dir: 'scale-out' | 'scale-in') {
    setBusy(true)
    setErr('')
    try {
      setResult(await intake<ScaleResult>(`/v1/ring/${dir}?worker=w4`, { method: 'POST' }))
      await load()
    } catch (x) {
      setErr((x as Error).message)
    } finally {
      setBusy(false)
    }
  }

  if (!data) return <p className="muted">{err || '加载中…'}</p>
  const moved = result ? new Set(result.moved_keys.map((m) => m.key)) : undefined
  const w4in = data.live.includes('w4')
  return (
    <>
      <h1>一致性哈希环</h1>
      <p className="sub">每个 worker 在环上有 {data.vnodes} 个虚拟节点（外圈刻度）；点是数据库里的 record id，颜色是它的主人。</p>
      <div className="grid2">
        <div className="card" style={{ display: 'flex', justifyContent: 'center' }}>
          <RingPicture data={data} moved={moved} testid="ring-svg" />
        </div>
        <div className="card">
          <h2 style={{ marginTop: 0 }}>成员与分布</h2>
          <table className="list">
            <thead><tr><th>worker</th><th>端口</th><th>在环上</th><th>心跳</th><th>key 数</th></tr></thead>
            <tbody>
              {Object.entries(data.members).map(([w, m]) => (
                <tr key={w} data-testid={`member-${w}`}>
                  <td><span style={{ color: COLORS[w], fontWeight: 700 }}>●</span> {w}</td>
                  <td className="mono">{m.port}</td>
                  <td>{m.active ? '是' : '待命'}</td>
                  <td>{m.alive ? <span className="pill ok">活着</span> : <span className="pill bad">超时</span>}</td>
                  <td className="mono" data-testid={`count-${w}`}>{data.counts[w] ?? 0}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="row" style={{ marginTop: 12 }}>
            <button className="primary" disabled={busy || w4in} onClick={() => scale('scale-out')} data-testid="scale-out">扩容：w4 加入</button>
            <button disabled={busy || !w4in} onClick={() => scale('scale-in')} data-testid="scale-in">缩容：w4 离开</button>
            {err && <span className="err">{err}</span>}
          </div>
          {result && (
            <div style={{ marginTop: 12 }} data-testid="scale-result">
              <div>
                检查了 <b>{result.keys_checked}</b> 个 key，换主人的有 <b data-testid="moved-count">{result.moved}</b> 个，
                比例 <b data-testid="moved-fraction">{(result.moved_fraction * 100).toFixed(1)}%</b>
                （理想值 {(result.expected_fraction * 100).toFixed(1)}%）。
              </div>
              <div className="muted" style={{ marginTop: 6 }}>
                搬家方向：{Array.from(new Set(result.moved_keys.map((m) => `${m.from}→${m.to}`))).join('、') || '无'}
              </div>
            </div>
          )}
        </div>
      </div>
      <h2>环的变更记录</h2>
      <div className="card">
        <table className="list">
          <thead><tr><th>epoch</th><th>之前</th><th>之后</th><th>原因</th></tr></thead>
          <tbody>
            {data.history.map((h) => (
              <tr key={h.epoch}><td className="mono">{h.epoch}</td><td>{h.before.join(', ')}</td><td>{h.after.join(', ')}</td><td>{h.reason}</td></tr>
            ))}
            {data.history.length === 0 && <tr><td colSpan={4} className="muted">还没有扩缩容过。</td></tr>}
          </tbody>
        </table>
      </div>
    </>
  )
}
