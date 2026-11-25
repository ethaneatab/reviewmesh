// Thin fetch helpers. The reviewer token comes from the Java login and is kept per browser.

const TOKEN_KEY = 'reviewmesh.session'

export type Session = { token: string; role: string; username: string; display_name: string }

export function session(): Session | null {
  try {
    const raw = localStorage.getItem(TOKEN_KEY)
    return raw ? (JSON.parse(raw) as Session) : null
  } catch {
    return null
  }
}

export function saveSession(s: Session | null) {
  try {
    if (s) localStorage.setItem(TOKEN_KEY, JSON.stringify(s))
    else localStorage.removeItem(TOKEN_KEY)
  } catch {
    /* private window: the session just lasts for this page */
  }
}

export class HttpError extends Error {
  constructor(public status: number, message: string) {
    super(message)
  }
}

async function call<T>(base: string, path: string, init: RequestInit = {}): Promise<T> {
  const s = session()
  const headers: Record<string, string> = { 'content-type': 'application/json', ...(init.headers as Record<string, string>) }
  if (s) headers.Authorization = `Bearer ${s.token}`
  const r = await fetch(base + path, { ...init, headers })
  const text = await r.text()
  const body = text ? JSON.parse(text) : null
  if (!r.ok) throw new HttpError(r.status, (body && (body.error || body.detail)) || r.statusText)
  return body as T
}

export const intake = <T,>(path: string, init?: RequestInit) => call<T>('/api/intake', path, init)
export const review = <T,>(path: string, init?: RequestInit) => call<T>('/api/review', path, init)
export const learn = <T,>(path: string, init?: RequestInit) => call<T>('/learn/api', path, init)

export async function login(username: string, password: string): Promise<Session> {
  const s = await call<Session>('/api/review', '/v1/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) })
  saveSession(s)
  return s
}

export type Task = {
  id: number
  record_id: string
  seq: number
  title: string
  doc_type: string
  queue: string
  priority: number
  status: string
  reviewer: string | null
  reviewer_id?: number | null
  decision_reason: string | null
  created_at: string
  updated_at: string
}

export type TimelineItem = { at: string; source: 'intake' | 'audit'; stage: string; actor: string; seq: number | null; detail: Record<string, unknown> }
export type Timeline = { record_id: string; status: string; trace_id: string; audit_available: boolean; items: TimelineItem[] }
