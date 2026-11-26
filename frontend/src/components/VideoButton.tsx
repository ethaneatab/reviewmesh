import { useState } from 'react'

/** Plays /videos/<part>.mp4 if it exists; otherwise says the video is not generated yet. */
export default function VideoButton({ src, testid }: { src: string; testid?: string }) {
  const [state, setState] = useState<'idle' | 'checking' | 'ok' | 'missing'>('idle')
  async function open() {
    if (state === 'ok') return setState('idle')
    setState('checking')
    try {
      const r = await fetch(src, { method: 'HEAD' })
      setState(r.ok && (r.headers.get('content-type') || '').includes('video') ? 'ok' : 'missing')
    } catch {
      setState('missing')
    }
  }
  return (
    <span data-testid={testid}>
      <button onClick={open} style={{ fontSize: 12, padding: '2px 8px' }}>看讲解视频</button>
      {state === 'missing' && <span className="muted" style={{ fontSize: 12, marginLeft: 6 }} data-testid="video-pending">视频待生成</span>}
      {state === 'ok' && (
        <div style={{ marginTop: 6 }}>
          <video src={src} controls autoPlay style={{ width: '100%', maxWidth: 560, borderRadius: 8 }} />
        </div>
      )}
    </span>
  )
}
