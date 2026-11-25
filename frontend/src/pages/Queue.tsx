import { useCallback, useEffect, useState } from 'react'
import { Link, Navigate } from 'react-router-dom'
import { Task, review, session } from '../api'

const QUEUES = ['all', 'finance', 'legal', 'claims', 'compliance', 'corrections', 'manual-triage', 'escalations']
const STATUSES = ['OPEN', 'CLAIMED', 'ESCALATED', 'APPROVED', 'REJECTED']

function statusPill(s: string) {
  const cls = s === 'APPROVED' ? 'ok' : s === 'REJECTED' ? 'bad' : s === 'ESCALATED' ? 'warn' : ''
  return <span className={`pill ${cls}`}>{s}</span>
}

export default function Queue() {
  const s = session()
  const [queue, setQueue] = useState('all')
  const [status, setStatus] = useState('OPEN')
  const [tasks, setTasks] = useState<Task[]>([])
  const [err, setErr] = useState('')

  const load = useCallback(async () => {
    try {
      const q = queue === 'all' ? '' : `&queue=${encodeURIComponent(queue)}`
      setTasks(await review<Task[]>(`/v1/tasks?status=${status}${q}`))
      setErr('')
    } catch (x) {
      setErr((x as Error).message)
    }
  }, [queue, status])

  useEffect(() => {
    load()
    const t = setInterval(load, 2000)
    return () => clearInterval(t)
  }, [load])

  if (!s) return <Navigate to="/login" replace />

  async function act(t: Task, action: 'claim' | 'approve' | 'reject' | 'escalate') {
    const reason = action === 'claim' ? undefined : window.prompt?.('原因（可留空）') ?? ''
    try {
      await review(`/v1/tasks/${t.id}/${action}`, { method: 'POST', body: action === 'claim' ? undefined : JSON.stringify({ reason }) })
      await load()
    } catch (x) {
      setErr((x as Error).message)
    }
  }

  const mine = (t: Task) => t.status === 'CLAIMED' && t.reviewer === s.username
  return (
    <>
      <h1>审核队列</h1>
      <p className="sub">认领一条，看完给出结论：通过、驳回，或者转人工（交给资深审核员）。</p>
      <div className="tabs">
        {QUEUES.map((q) => (
          <button key={q} className={q === queue ? 'on' : ''} onClick={() => setQueue(q)} data-testid={`queue-${q}`}>{q}</button>
        ))}
      </div>
      <div className="row" style={{ marginBottom: 10 }}>
        <label className="muted">状态</label>
        <select value={status} onChange={(e) => setStatus(e.target.value)} data-testid="status-filter">
          {STATUSES.map((x) => <option key={x}>{x}</option>)}
        </select>
        {err && <span className="err">{err}</span>}
      </div>
      <div className="card">
        <table className="list" data-testid="task-table">
          <thead>
            <tr><th>#</th><th>标题</th><th>队列</th><th>优先级</th><th>状态</th><th>审核员</th><th>操作</th></tr>
          </thead>
          <tbody>
            {tasks.map((t) => (
              <tr key={t.id} data-testid={`task-${t.record_id}`}>
                <td className="mono">{t.id}</td>
                <td><Link to={`/records/${t.record_id}`}>{t.title}</Link><div className="muted mono">{t.record_id} · v{t.seq}</div></td>
                <td>{t.queue}</td>
                <td>{['', '高', '中', '低'][t.priority] ?? t.priority}</td>
                <td>{statusPill(t.status)}</td>
                <td>{t.reviewer ?? '—'}</td>
                <td className="row">
                  {(t.status === 'OPEN' || (t.status === 'ESCALATED' && s.role === 'senior')) && (
                    <button className="primary" onClick={() => act(t, 'claim')} data-testid="claim">认领</button>
                  )}
                  {mine(t) && (
                    <>
                      <button onClick={() => act(t, 'approve')} data-testid="approve">通过</button>
                      <button className="danger" onClick={() => act(t, 'reject')} data-testid="reject">驳回</button>
                      <button className="warn" onClick={() => act(t, 'escalate')} data-testid="escalate">转人工</button>
                    </>
                  )}
                </td>
              </tr>
            ))}
            {tasks.length === 0 && <tr><td colSpan={7} className="muted">这个队列现在是空的。</td></tr>}
          </tbody>
        </table>
      </div>
    </>
  )
}
