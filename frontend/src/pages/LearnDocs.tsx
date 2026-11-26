import interviewMd from '../../../docs/interview.md?raw'
import problemsMd from '../../../docs/problems.md?raw'
import Markdown, { sections } from '../components/Markdown'
import VideoButton from '../components/VideoButton'

export default function LearnDocs({ kind }: { kind: 'interview' | 'problems' }) {
  const groups = sections(kind === 'interview' ? interviewMd : problemsMd)
  if (kind === 'problems') {
    return (
      <div data-testid="problems">
        {groups.map((g, gi) => {
          const id = g.title.split(/\s/)[0]
          return (
            <details key={gi} className="card qa" data-testid={`problem-${id}`} style={{ marginBottom: 10 }}>
              <summary><b>{g.title}</b></summary>
              <VideoButton src={`/videos/problems/${id}.mp4`} testid={`problem-video-${id}`} />
              {g.items.map((it, i) => (
                <div key={i} data-testid={`problem-${id}-section-${i}`}>
                  {it.title && <h3 style={{ fontSize: 14, marginBottom: 4 }}>{it.title}</h3>}
                  <Markdown text={it.body} />
                </div>
              ))}
            </details>
          )
        })}
      </div>
    )
  }
  return (
    <div data-testid="interview">
      {groups.map((g, gi) => (
        <section key={gi}>
          <h2>{g.title}</h2>
          {g.items.map((it, i) => (
            <details key={i} className="card qa" style={{ marginBottom: 8 }} data-testid={`q-${gi}-${i}`}>
              <summary>{it.title}</summary>
              <div data-testid="answer"><Markdown text={it.body} /></div>
            </details>
          ))}
        </section>
      ))}
    </div>
  )
}
