import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Timeline, intake } from '../api'
import Json from '../components/Json'

export default function RecordPage() {
  const { id = '' } = useParams()
  const [tl, setTl] = useState<Timeline | null>(null)
  const [open, setOpen] = useState<number | null>(null)
  const [err, setErr] = useState('')
  useEffect(() => {
    let live = true
    const load = () => intake<Timeline>(`/v1/records/${id}/timeline`).then((t) => live && setTl(t)).catch((e) => setErr(e.message))
    load()
    const t = setInterval(load, 2000)
    return () => { live = false; clearInterval(t) }
  }, [id])
  if (err) return <p className="err">{err}</p>
  if (!tl) return <p className="muted">加载中…</p>
  return (
    <>
      <h1>记录 <span className="mono">{id}</span></h1>
      <p className="sub">
        当前状态 <span className="pill" data-testid="record-status">{tl.status}</span> · trace <span className="mono">{tl.trace_id}</span>
        {!tl.audit_available && <span className="err"> · 审计服务暂时不可用，下面只有 intake 一侧的事件</span>}
      </p>
      <div className="card">
        <ul className="timeline" data-testid="timeline">
          {tl.items.map((it, i) => (
            <li key={i} className={it.source} data-testid={`tl-${it.stage}`}>
              <div className="row">
                <span className="when">{it.at.slice(11, 23)}</span>
                <b>{it.stage}</b>
                <span className="muted">{it.actor}</span>
                {it.seq != null && <span className="pill">v{it.seq}</span>}
                <span className={`pill ${it.source === 'audit' ? 'warn' : ''}`}>{it.source === 'audit' ? 'Java 审计' : 'Python'}</span>
                <button onClick={() => setOpen(open === i ? null : i)} data-testid={`tl-toggle-${it.stage}`}>{open === i ? '收起' : '详情'}</button>
              </div>
              {open === i && <Json value={it.detail} testid={`tl-json-${it.stage}`} />}
            </li>
          ))}
        </ul>
      </div>
    </>
  )
}
