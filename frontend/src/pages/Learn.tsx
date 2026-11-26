import { useCallback, useEffect, useRef, useState } from 'react'
import { NavLink, Route, Routes, useSearchParams } from 'react-router-dom'
import { HttpError, intake, learn, review } from '../api'
import Json from '../components/Json'
import SourceLink from '../components/SourceLink'
import VideoButton from '../components/VideoButton'
import LearnDocs from './LearnDocs'
import { RingPicture } from './Ring'
import { ErrorChart, RolloutView, StageLadder } from './Rollout'

type Stage = { id: string; label: string; part: string; anchor: string; status: 'done' | 'pending'; at: string | null; data: unknown }
type Run = { record_id: string; status: string; stages: Stage[]; task: { id: number; status: string } | null }

/** The one-line takeaway for each stage, shown next to its real data. */
const KEY_VALUE: Record<string, (d: any) => string> = {
  submit: (d) => `重试同一个 key：HTTP ${d?.retry_same_key?.status}，replay=${d?.retry_same_key?.replayed}`,
  s3: (d) => `${d?.key} · ${d?.bytes} 字节`,
  lambda: (d) => (d?.fallback ? `Lambda 没来，reconciler 兜底` : `request ${String(d?.lambda_request_id).slice(0, 8)} · sniff=${d?.sniff}`),
  sqs: (d) => `message ${String(d?.message_id).slice(0, 8)} · 第 ${d?.receive_count} 次收到`,
  partition: (d) => `环上 ${d?.angle}° → ${d?.vnode} → ${d?.owner}（epoch ${d?.epoch}）`,
  validate: (d) => `passed=${d?.passed} · risk ${d?.risk_score}`,
  route: (d) => `${d?.engine} → ${d?.queue}（优先级 ${d?.priority}）`,
  claim: (d) => `${d?.reviewer}：${d?.from} → ${d?.to}`,
  audit: (d) => `${d?.trail?.length} 条审计`,
  export: (d) => `${d?.key}`,
}

function MainLine() {
  // The run id lives in the URL (?run=rec_…), so leaving for a branch tab and coming back keeps it.
  const [params, setParams] = useSearchParams()
  const rid = params.get('run')
  const [run, setRun] = useState<Run | null>(null)
  const [open, setOpen] = useState<string | null>(null)
  const [err, setErr] = useState('')
  const timer = useRef<number>()

  const poll = useCallback(async (id: string) => {
    try {
      setRun(await learn<Run>(`/runs/${id}`))
    } catch (x) {
      setErr((x as Error).message)
    }
  }, [])

  useEffect(() => {
    if (!rid) return
    poll(rid)
    timer.current = window.setInterval(() => poll(rid), 800)
    return () => window.clearInterval(timer.current)
  }, [rid, poll])

  async function submit() {
    setErr('')
    setRun(null)
    setOpen(null)
    const r = await learn<{ record_id: string }>('/runs', { method: 'POST' })
    setParams({ run: r.record_id })
  }

  async function act(what: 'claim' | 'approve') {
    if (!rid) return
    try {
      await learn(`/runs/${rid}/${what}`, { method: 'POST' })
      await poll(rid)
    } catch (x) {
      setErr(x instanceof HttpError ? `${x.status} ${x.message}` : String(x))
    }
  }

  const done = (id: string) => run?.stages.find((s) => s.id === id)?.status === 'done'
  return (
    <>
      <div className="row" style={{ marginBottom: 12 }}>
        <button className="primary" onClick={submit} data-testid="learn-submit">提交样例</button>
        {rid && <span className="mono" data-testid="learn-record">{rid}</span>}
        {run && <span className="pill" data-testid="learn-status">{run.status}</span>}
        {err && <span className="err">{err}</span>}
      </div>
      <p className="muted" style={{ marginTop: -4 }}>每一步亮起的条件，是后端真的有了那一行数据：Postgres 的事件、S3 的对象、Java 的审计记录。页面每 0.8 秒问一次。</p>
      <ol className="stages" data-testid="stages">
        {(run?.stages ?? []).map((s, i) => (
          <li key={s.id} className={`stage ${s.status}`} data-testid={`stage-${s.id}`} data-status={s.status}>
            <div className="stage-head">
              <span className="stage-no">{i + 1}</span>
              <b>{s.label}</b>
              {s.at && <span className="when mono">{s.at.slice(11, 23)}</span>}
              {s.status === 'done' && <span className="key-value" data-testid={`kv-${s.id}`}>{KEY_VALUE[s.id]?.(s.data)}</span>}
              <span style={{ marginLeft: 'auto' }} className="row">
                <SourceLink anchor={s.anchor} testid={`src-${s.id}`} />
                <VideoButton src={`/videos/${s.part}.mp4`} testid={`video-${s.id}`} />
                {s.status === 'done' && (
                  <button onClick={() => setOpen(open === s.id ? null : s.id)} data-testid={`open-${s.id}`} style={{ fontSize: 12, padding: '2px 8px' }}>
                    {open === s.id ? '收起数据' : '看数据'}
                  </button>
                )}
              </span>
            </div>
            {s.id === 'claim' && done('route') && !done('claim') && (
              <div className="row" style={{ margin: '6px 0 0 34px' }}>
                <button className="primary" onClick={() => act('claim')} data-testid="learn-claim">以审核员 rita 认领</button>
              </div>
            )}
            {s.id === 'audit' && done('claim') && !done('audit') && (
              <div className="row" style={{ margin: '6px 0 0 34px' }}>
                <button className="primary" onClick={() => act('approve')} data-testid="learn-approve">通过</button>
              </div>
            )}
            {open === s.id && <div style={{ marginLeft: 34 }}><Json value={s.data} testid={`data-${s.id}`} /></div>}
          </li>
        ))}
      </ol>
      {!run && <p className="muted">点「提交样例」开始：会提交一张样例发票，并且用同一个幂等键再发一次。</p>}
    </>
  )
}

function ScaleBranch() {
  const [ring, setRing] = useState<any>(null)
  const [res, setRes] = useState<any>(null)
  const load = useCallback(() => intake<any>('/v1/ring?sample=600').then(setRing), [])
  useEffect(() => { load() }, [load])
  async function scale(dir: string) {
    setRes(await intake(`/v1/ring/${dir}?worker=w4`, { method: 'POST' }))
    await load()
  }
  if (!ring) return <p className="muted">加载中…</p>
  const w4 = ring.live.includes('w4')
  return (
    <div className="grid2">
      <div className="card" style={{ display: 'flex', justifyContent: 'center' }}>
        <RingPicture data={ring} moved={res ? new Set(res.moved_keys.map((m: any) => m.key)) : undefined} testid="branch-ring" />
      </div>
      <div className="card">
        <p>环上现在有 <b data-testid="branch-live">{ring.live.join('、')}</b>，epoch {ring.epoch}。点扩容，w4 加入环，看哪些 key 换了主人。</p>
        <div className="row">
          <button className="primary" disabled={w4} onClick={() => scale('scale-out')} data-testid="branch-scale-out">扩容：w4 加入</button>
          <button disabled={!w4} onClick={() => scale('scale-in')} data-testid="branch-scale-in">缩容：w4 离开</button>
        </div>
        {res && (
          <div style={{ marginTop: 10 }} data-testid="branch-scale-result">
            <p>
              检查 {res.keys_checked} 个 key，搬了 <b className="key-value" data-testid="branch-moved">{res.moved}</b> 个，
              比例 <b className="key-value" data-testid="branch-fraction">{(res.moved_fraction * 100).toFixed(1)}%</b>，理想值 {(res.expected_fraction * 100).toFixed(1)}%。
            </p>
            <Json value={res.moved_sample.slice(0, 5)} testid="branch-moved-sample" />
          </div>
        )}
        <p className="row" style={{ marginTop: 10 }}>
          <SourceLink anchor="ring-lookup" testid="branch-src-ring" />
          <SourceLink anchor="record-lock" />
          <SourceLink anchor="fenced-commit" />
          <VideoButton src="/videos/p3-partition.mp4" />
        </p>
      </div>
    </div>
  )
}

function RolloutBranch() {
  const [v, setV] = useState<RolloutView | null>(null)
  const [err, setErr] = useState('')
  const load = useCallback(() => review<RolloutView>('/v1/rollout').then(setV), [])
  useEffect(() => {
    load()
    const t = setInterval(load, 1000)
    return () => clearInterval(t)
  }, [load])
  async function act(path: string) {
    setErr('')
    try { await intake(path, { method: 'POST' }); await load() } catch (x) { setErr((x as Error).message) }
  }
  if (!v) return <p className="muted">加载中…</p>
  const rb = v.events.find((e) => e.kind === 'ROLLBACK')
  return (
    <div className="grid2">
      <div className="card">
        <div className="row" style={{ alignItems: 'baseline' }}>
          <span style={{ fontSize: 34, fontWeight: 800, color: 'var(--v2)' }} data-testid="branch-percent">{v.percent}%</span>
          <span className="pill" data-testid="branch-rollout-status">{v.status}</span>
        </div>
        <StageLadder data={v} />
        <p className="muted">窗口内 v2 <b data-testid="branch-samples">{v.window.samples}</b> 次，错误率 <b data-testid="branch-rate">{(v.window.error_rate * 100).toFixed(1)}%</b>，阈值 {(v.config.threshold * 100).toFixed(0)}%</p>
        <div className="row">
          <button onClick={() => act('/v1/rollout/reset')} data-testid="branch-reset">重置</button>
          <button className="primary" onClick={() => act('/v1/rollout/start')} data-testid="branch-start">开始放量</button>
          <button onClick={() => act('/v1/rollout/advance')} data-testid="branch-advance">下一档</button>
          <button onClick={() => act('/v1/rollout/traffic?seconds=40&rps=100')} data-testid="branch-traffic">模拟流量</button>
          <button className="danger" onClick={() => act('/v1/rollout/fault?rate=0.4')} data-testid="branch-fault">注入四成故障</button>
        </div>
        {err && <p className="err">{err}</p>}
        {rb && <p data-testid="branch-rollback"><span className="pill bad">自动回滚</span> <span className="key-value" data-testid="branch-rollback-reason">{rb.reason}</span></p>}
        <p className="row"><SourceLink anchor="rollback-decision" testid="branch-src-rollback" /><SourceLink anchor="flag-choose" /><VideoButton src="/videos/p7-rollout.mp4" /></p>
      </div>
      <div className="card"><ErrorChart data={v} /></div>
    </div>
  )
}

function MigrationBranch() {
  const [m, setM] = useState<any>(null)
  useEffect(() => { learn<any>('/migration').then(setM) }, [])
  if (!m) return <p className="muted">加载中…</p>
  return (
    <div className="grid2">
      <div className="card">
        <p>当前版本的 phase：<b className="key-value" data-testid="migr-phase">{m.phase}</b></p>
        <p>review_tasks 的列：<span className="mono" data-testid="migr-columns">{m.review_tasks_columns.join(', ')}</span></p>
        <p>旧的文本列 reviewer 还在吗？<b data-testid="migr-text">{m.has_reviewer_text ? '在' : '已删除（contract 完成）'}</b> · 待回填 {m.pending_backfill} 行</p>
        <p className="row"><SourceLink anchor="phase-sql" testid="migr-src" /><SourceLink anchor="backfill" /><SourceLink anchor="test-expand-contract" /><VideoButton src="/videos/p6-migration.mp4" /></p>
      </div>
      <div className="card">
        <table className="list" data-testid="migr-history">
          <thead><tr><th>版本</th><th>迁移</th><th>时间</th></tr></thead>
          <tbody>{m.schema_history.map((h: any) => <tr key={h.version}><td className="mono">V{h.version}</td><td>{h.description}</td><td className="mono">{String(h.installed_on).slice(0, 19)}</td></tr>)}</tbody>
        </table>
      </div>
    </div>
  )
}

export default function Learn() {
  return (
    <>
      <h1>教学模式</h1>
      <div className="tabs">
        <NavLink end to="/learn" className={({ isActive }) => (isActive ? 'on' : '')} data-testid="tab-main">主线：一份文档走完全程</NavLink>
        <NavLink to="/learn/scale" className={({ isActive }) => (isActive ? 'on' : '')} data-testid="tab-scale">支线：扩容</NavLink>
        <NavLink to="/learn/rollout" className={({ isActive }) => (isActive ? 'on' : '')} data-testid="tab-rollout">支线：灰度与回滚</NavLink>
        <NavLink to="/learn/migration" className={({ isActive }) => (isActive ? 'on' : '')} data-testid="tab-migration">支线：表结构迁移</NavLink>
        <NavLink to="/learn/interview" className={({ isActive }) => (isActive ? 'on' : '')} data-testid="tab-interview">面试题</NavLink>
        <NavLink to="/learn/problems" className={({ isActive }) => (isActive ? 'on' : '')} data-testid="tab-problems">日常问题</NavLink>
      </div>
      <Routes>
        <Route index element={<MainLine />} />
        <Route path="scale" element={<ScaleBranch />} />
        <Route path="rollout" element={<RolloutBranch />} />
        <Route path="migration" element={<MigrationBranch />} />
        <Route path="interview" element={<LearnDocs kind="interview" />} />
        <Route path="problems" element={<LearnDocs kind="problems" />} />
      </Routes>
    </>
  )
}
