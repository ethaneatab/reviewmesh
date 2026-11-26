import { ReactNode } from 'react'
import { sourceUrl } from './SourceLink'

/** Just enough markdown for docs/interview.md and docs/problems.md: paragraphs, lists, code, bold, links, tables. */
function inline(text: string, key: string): ReactNode[] {
  const out: ReactNode[] = []
  const re = /(`[^`]+`|\*\*[^*]+\*\*|\[[^\]]+\]\([^)]+\))/g
  let last = 0
  let m: RegExpExecArray | null
  let i = 0
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index))
    const t = m[0]
    if (t.startsWith('`')) out.push(<code key={`${key}-${i++}`}>{t.slice(1, -1)}</code>)
    else if (t.startsWith('**')) out.push(<b key={`${key}-${i++}`}>{t.slice(2, -2)}</b>)
    else {
      const [, label, href] = /\[([^\]]+)\]\(([^)]+)\)/.exec(t)!
      const url = href.startsWith('anchor:') ? sourceUrl(href.slice(7)) : href
      out.push(<a key={`${key}-${i++}`} href={url} target="_blank" rel="noreferrer">{label}</a>)
    }
    last = m.index + t.length
  }
  if (last < text.length) out.push(text.slice(last))
  return out
}

export default function Markdown({ text }: { text: string }) {
  const lines = text.split('\n')
  const blocks: ReactNode[] = []
  let i = 0
  let k = 0
  while (i < lines.length) {
    const line = lines[i]
    if (line.startsWith('```')) {
      const body: string[] = []
      i++
      while (i < lines.length && !lines[i].startsWith('```')) body.push(lines[i++])
      i++
      blocks.push(<div className="json" key={k++}><pre>{body.join('\n')}</pre></div>)
    } else if (/^\s*[-*] /.test(line) || /^\s*\d+\. /.test(line)) {
      const items: string[] = []
      while (i < lines.length && (/^\s*[-*] /.test(lines[i]) || /^\s*\d+\. /.test(lines[i]))) items.push(lines[i++].replace(/^\s*([-*]|\d+\.) /, ''))
      blocks.push(<ul key={k++}>{items.map((t, j) => <li key={j}>{inline(t, `${k}-${j}`)}</li>)}</ul>)
    } else if (line.startsWith('|')) {
      const rows: string[][] = []
      while (i < lines.length && lines[i].startsWith('|')) {
        const cells = lines[i++].split('|').slice(1, -1).map((c) => c.trim())
        if (!cells.every((c) => /^-+$/.test(c))) rows.push(cells)
      }
      blocks.push(
        <table className="list" key={k++}><tbody>{rows.map((r, j) => <tr key={j}>{r.map((c, n) => j === 0 ? <th key={n}>{inline(c, `${k}-${j}-${n}`)}</th> : <td key={n}>{inline(c, `${k}-${j}-${n}`)}</td>)}</tr>)}</tbody></table>,
      )
    } else if (/^#{4,} /.test(line)) {
      blocks.push(<h4 key={k++} style={{ margin: '12px 0 4px' }}>{inline(line.replace(/^#+ /, ''), `h${k}`)}</h4>)
      i++
    } else if (line.trim() === '' || line.startsWith('> ')) {
      if (line.startsWith('> ')) blocks.push(<p key={k++} className="muted">{inline(line.slice(2), `q${k}`)}</p>)
      i++
    } else {
      const para: string[] = []
      while (i < lines.length && lines[i].trim() !== '' && !/^(```|\s*[-*] |\s*\d+\. |\||#)/.test(lines[i])) para.push(lines[i++])
      if (para.length === 0) { i++; continue }
      blocks.push(<p key={k++}>{inline(para.join(' '), `p${k}`)}</p>)
    }
  }
  return <div className="md">{blocks}</div>
}

/** Split a document into `## group` -> `### item` sections. */
export function sections(md: string) {
  const groups: { title: string; items: { title: string; body: string }[] }[] = []
  for (const chunk of md.split(/^## /m).slice(1)) {
    const [head, ...rest] = chunk.split('\n')
    const body = rest.join('\n')
    const items = body.split(/^### /m).slice(1).map((c) => {
      const [t, ...b] = c.split('\n')
      return { title: t.trim(), body: b.join('\n') }
    })
    groups.push({ title: head.trim(), items: items.length ? items : [{ title: '', body }] })
  }
  return groups
}
