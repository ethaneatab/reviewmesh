import { useEffect, useState } from 'react'
import { intake } from '../api'

type Overview = {
  queues: Record<string, number>
  records_by_status: Record<string, number>
  stuck: number
  workers: Record<string, { active: boolean; alive: boolean }>
  rollout: { percent: number; status: string }
  alerts: { name: string; severity: string; detail: string }[]
}

export default function Ops() {
  const [o, setO] = useState<Overview | null>(null)
  useEffect(() => {
    const load = () => intake<Overview>('/v1/ops/overview').then(setO)
    load()
    const t = setInterval(load, 3000)
    return () => clearInterval(t)
  }, [])
  if (!o) return <p className="muted">加载中…</p>
  return (
    <>
      <h1>运维总览</h1>
      <p className="sub">同样的条件也写成了 Prometheus 告警规则（ops/prometheus/alerts.yml）；这里不用起 Prometheus 也能看。</p>
      <div className="card" style={{ marginBottom: 14 }} data-testid="alerts">
        <h2 style={{ marginTop: 0 }}>告警</h2>
        {o.alerts.length === 0 ? <p className="muted">没有告警。</p> : o.alerts.map((a, i) => (
          <p key={i} data-testid={`alert-${a.name}`}><span className={`pill ${a.severity === 'page' ? 'bad' : 'warn'}`}>{a.name}</span> {a.detail}</p>
        ))}
      </div>
      <div className="grid2">
        <div className="card">
          <h2 style={{ marginTop: 0 }}>SQS 队列深度</h2>
          <table className="list"><tbody>
            {Object.entries(o.queues).map(([q, n]) => (
              <tr key={q} data-testid={`queue-depth-${q}`}><td className="mono">{q}</td><td className="mono">{n}</td><td>{q.endsWith('dlq') && n > 0 ? <span className="pill bad">死信</span> : null}</td></tr>
            ))}
          </tbody></table>
        </div>
        <div className="card">
          <h2 style={{ marginTop: 0 }}>记录状态</h2>
          <table className="list"><tbody>
            {Object.entries(o.records_by_status).map(([s, n]) => <tr key={s}><td>{s}</td><td className="mono">{n}</td></tr>)}
          </tbody></table>
          <p>卡在 STORED 超过二十秒：<b>{o.stuck}</b> · 灰度：{o.rollout?.status} {o.rollout?.percent}%</p>
          <p>worker：{Object.entries(o.workers).map(([w, i]) => `${w}${i.active ? '' : '(待命)'}${i.alive ? '' : '✗'}`).join('  ')}</p>
        </div>
      </div>
    </>
  )
}
