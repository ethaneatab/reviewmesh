import { useCallback, useEffect, useState } from 'react'
import { intake, review } from '../api'

export type RolloutView = {
  percent: number
  status: string
  fault_rate: number
  window: { samples: number; errors: number; error_rate: number; seconds: number }
  config: { threshold: number; min_samples: number; hold_seconds: number; stages: number[] }
  series: { t: number; v2: number; v2_errors: number; v1: number }[]
  events: { id: number; kind: string; from_pct: number | null; to_pct: number | null; reason: string; error_rate: number | null; samples: number | null; at: string }[]
}

export function ErrorChart({ data }: { data: RolloutView }) {
  const W = 640, H = 170, P = 28
  const s = data.series
  const x = (i: number) => P + (i * (W - 2 * P)) / Math.max(1, s.length - 1)
  const maxN = Math.max(5, ...s.map((p) => p.v2))
  const y = (rate: number) => H - P - rate * (H - 2 * P)
  const pts = s.map((p, i) => (p.v2 ? `${x(i)},${y(p.v2_errors / p.v2)}` : null)).filter(Boolean).join(' ')
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" data-testid="error-chart" role="img" aria-label="v2 error rate">
      {s.map((p, i) => (
        <rect key={i} x={x(i) - 2} width={4} y={H - P - (p.v2 / maxN) * (H - 2 * P) * 0.5} height={(p.v2 / maxN) * (H - 2 * P) * 0.5} fill="#fbcfe8" />
      ))}
      <line x1={P} x2={W - P} y1={y(data.config.threshold)} y2={y(data.config.threshold)} stroke="var(--bad)" strokeDasharray="5 4" />
      <text x={W - P} y={y(data.config.threshold) - 4} textAnchor="end" fontSize={11} fill="var(--bad)">阈值 {(data.config.threshold * 100).toFixed(0)}%</text>
      <polyline points={pts} fill="none" stroke="var(--v2)" strokeWidth={2} />
      <line x1={P} x2={W - P} y1={H - P} y2={H - P} stroke="var(--line)" />
      <text x={P} y={14} fontSize={11} fill="var(--muted)">v2 每秒错误率（线）与请求数（浅色柱），最近 {s.length} 秒</text>
    </svg>
  )
}

export function StageLadder({ data }: { data: RolloutView }) {
  return (
    <div className="row" data-testid="stage-ladder">
      {[0, ...data.config.stages].map((st) => (
        <span key={st} className={`pill ${data.percent === st ? (data.status === 'ROLLED_BACK' ? 'bad' : 'v2') : ''}`} data-testid={`stage-${st}`}
          style={{ opacity: data.percent === st ? 1 : 0.55, fontWeight: data.percent === st ? 700 : 400 }}>
          {st}%
        </span>
      ))}
    </div>
  )
}

export default function Rollout() {
  const [data, setData] = useState<RolloutView | null>(null)
  const [fault, setFault] = useState(40)
  const [err, setErr] = useState('')
  const load = useCallback(() => review<RolloutView>('/v1/rollout').then(setData).catch((e) => setErr(e.message)), [])
  useEffect(() => {
    load()
    const t = setInterval(load, 1000)
    return () => clearInterval(t)
  }, [load])

  async function act(path: string) {
    setErr('')
    try {
      await intake(path, { method: 'POST' })
      await load()
    } catch (x) {
      setErr((x as Error).message)
    }
  }

  if (!data) return <p className="muted">{err || '加载中…'}</p>
  const rb = data.events.find((e) => e.kind === 'ROLLBACK')
  return (
    <>
      <h1>发布控制台 · routing-v2</h1>
      <p className="sub">新路由逻辑按 1% → 10% → 50% → 100% 放量；控制器每半秒看一次 v2 最近 {data.window.seconds} 秒的错误率，超过阈值就自动退回 0%。</p>
      <div className="grid2">
        <div className="card">
          <div className="row" style={{ alignItems: 'baseline' }}>
            <span style={{ fontSize: 40, fontWeight: 800, color: 'var(--v2)' }} data-testid="rollout-percent">{data.percent}%</span>
            <span className={`pill ${data.status === 'ROLLED_BACK' ? 'bad' : data.status === 'COMPLETE' ? 'ok' : ''}`} data-testid="rollout-status">{data.status}</span>
            {data.fault_rate > 0 && <span className="pill warn">故障注入 {(data.fault_rate * 100).toFixed(0)}%</span>}
          </div>
          <StageLadder data={data} />
          <p className="muted">
            窗口内 v2：<b data-testid="window-samples">{data.window.samples}</b> 次，错误 {data.window.errors} 次，错误率{' '}
            <b data-testid="window-rate">{(data.window.error_rate * 100).toFixed(1)}%</b>（至少 {data.config.min_samples} 次才判断）
          </p>
          <div className="row">
            <button className="primary" onClick={() => act('/v1/rollout/start')} data-testid="rollout-start">开始放量（1%）</button>
            <button onClick={() => act('/v1/rollout/advance')} data-testid="rollout-advance">下一档</button>
            <button onClick={() => act('/v1/rollout/traffic?seconds=40&rps=100')} data-testid="rollout-traffic">模拟流量 40 秒</button>
            <button onClick={() => act('/v1/rollout/reset')} data-testid="rollout-reset">重置</button>
          </div>
          <div className="row" style={{ marginTop: 10 }}>
            <label className="muted">让 v2 出错</label>
            <input type="range" min={0} max={80} value={fault} onChange={(e) => setFault(+e.target.value)} />
            <span className="mono">{fault}%</span>
            <button className="danger" onClick={() => act(`/v1/rollout/fault?rate=${fault / 100}`)} data-testid="rollout-fault">注入故障</button>
            <button onClick={() => act('/v1/rollout/fault?rate=0')}>清除故障</button>
          </div>
          {err && <p className="err">{err}</p>}
          {rb && <p data-testid="rollback-reason"><span className="pill bad">自动回滚</span> {rb.reason}</p>}
        </div>
        <div className="card"><ErrorChart data={data} /></div>
      </div>
      <h2>放量与回滚记录</h2>
      <div className="card">
        <table className="list" data-testid="rollout-events">
          <thead><tr><th>时间</th><th>动作</th><th>放量</th><th>原因</th></tr></thead>
          <tbody>
            {data.events.map((e) => (
              <tr key={e.id} data-testid={`event-${e.kind}`}>
                <td className="mono">{e.at.slice(11, 19)}</td>
                <td><span className={`pill ${e.kind === 'ROLLBACK' ? 'bad' : e.kind === 'FAULT' ? 'warn' : ''}`}>{e.kind}</span></td>
                <td className="mono">{e.from_pct ?? ''}{e.to_pct != null ? ` → ${e.to_pct}%` : ''}</td>
                <td>{e.reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}
