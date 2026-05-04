import { Info } from 'lucide-react'
import { useMemo, useState } from 'react'
import type { FilingDiff as FilingDiffType } from '../types/stock'
import { Shimmer } from './SkeletonReport'

export default function FilingDiff({ diff, loaded }: { diff: FilingDiffType | null; loaded: boolean }) {
  const [active, setActive] = useState(0)
  const [expanded, setExpanded] = useState(false)
  const section = diff?.changed_sections[active]
  const visibleLines = useMemo(() => {
    if (!section) return []
    const lines = [
      ...section.additions.map((text) => ({ type: 'add' as const, text })),
      ...section.deletions.map((text) => ({ type: 'delete' as const, text })),
    ]
    return expanded ? lines : lines.slice(0, 10)
  }, [expanded, section])

  if (!loaded || !diff) {
    return (
      <section className="section-card">
        <h2 className="section-title">What changed</h2>
        <Shimmer height={32} />
        <div style={{ height: 10 }} />
        <Shimmer height={130} />
      </section>
    )
  }

  return (
    <section className="section-card">
      <h2 className="section-title" title="Changes in SEC filings often signal important shifts before headlines. Red text = removed disclosures. Green text = new disclosures.">
        What changed: {diff.ticker} {diff.filing_type} {diff.current_period} vs {diff.prior_period}
        <Info size={15} className="muted" />
      </h2>
      <div className="diff-tabs">
        {diff.changed_sections.map((item, index) => (
          <button
            type="button"
            key={item.section_name}
            className="tab-button"
            data-state={index === active ? 'active' : 'inactive'}
            onClick={() => {
              setActive(index)
              setExpanded(false)
            }}
          >
            {item.section_name}
          </button>
        ))}
      </div>
      {section ? (
        <>
          <p className="muted" style={{ marginTop: 0 }}>{section.summary}</p>
          <div style={{ marginTop: 12 }}>
            {visibleLines.map((line, index) => (
              <div
                key={`${line.type}-${index}-${line.text}`}
                className={`diff-line ${line.type === 'add' ? 'diff-add' : line.type === 'delete' ? 'diff-del' : 'diff-context'}`}
                aria-label={line.type === 'add' ? 'Addition:' : line.type === 'delete' ? 'Deletion:' : undefined}
              >
                <span>{line.type === 'add' ? '+' : line.type === 'delete' ? '-' : ' '}</span>
                <span>{line.text}</span>
              </div>
            ))}
          </div>
          {section.additions.length + section.deletions.length > 10 ? (
            <button type="button" className="text-button" onClick={() => setExpanded((current) => !current)}>
              {expanded ? 'Show less' : `Show ${section.additions.length + section.deletions.length - 10} more`}
            </button>
          ) : null}
        </>
      ) : (
        <p className="muted">No material changes detected in this section.</p>
      )}
    </section>
  )
}
