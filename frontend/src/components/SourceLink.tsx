import anchors from '../generated/anchors.json'

type Anchor = { path: string; start: number; end: number }
const table = anchors as Record<string, Anchor>

/** GitHub link to the exact lines of an @learn anchor, pinned to the commit the page was built from. */
export function sourceUrl(anchor: string): string {
  const a = table[anchor]
  if (!a) return ''
  return `${__REPO_URL__}/blob/${__GIT_SHA__}/${a.path}#L${a.start}-L${a.end}`
}

export default function SourceLink({ anchor, testid }: { anchor: string; testid?: string }) {
  const a = table[anchor]
  if (!a) return <span className="err">锚点缺失：{anchor}</span>
  return (
    <a href={sourceUrl(anchor)} target="_blank" rel="noreferrer" data-testid={testid} data-anchor={anchor} className="mono" style={{ fontSize: 12 }}>
      看源码 {a.path.split('/').pop()}:{a.start}
    </a>
  )
}
