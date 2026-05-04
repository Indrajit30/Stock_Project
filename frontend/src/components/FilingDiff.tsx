import { Info } from 'lucide-react'
import { useState } from 'react'
import type { FilingDiff as FilingDiffType } from '../types/stock'
import { Shimmer } from './SkeletonReport'

export default function FilingDiff({ diff, loaded }: { diff: FilingDiffType | null; loaded: boolean }) {
  const [active, setActive] = useState(0)
  const section = diff?.changed_sections[active]

  if (!loaded || !diff) {
    return (
      <section className="section-card">
        <h2 className="section-title">What changed</h2>
        <Shimmer height={32} />
        <div style={{ height: 10 }} />
        <Shimmer height={160} />
      </section>
    )
  }

  return (
    <section className="section-card">
      <h2
        className="section-title"
        title="Changes in SEC filings often signal important shifts before headlines. Green = positive development. Red = negative development."
      >
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
            onClick={() => setActive(index)}
          >
            {item.section_name}
          </button>
        ))}
      </div>

      {section ? (
        <>
          <p className="muted" style={{ marginTop: 0 }}>{section.summary}</p>
          <div className="diff-columns">
            <div className="diff-col">
              <div className="diff-col-header diff-col-header-positive">Positives</div>
              {section.positives.length === 0 ? (
                <p className="muted diff-col-empty">No positive changes detected.</p>
              ) : (
                section.positives.map((text, i) => (
                  <div key={i} className="diff-item diff-item-positive">
                    <span className="diff-item-icon">↑</span>
                    <span>{text}</span>
                  </div>
                ))
              )}
            </div>
            <div className="diff-col">
              <div className="diff-col-header diff-col-header-negative">Negatives</div>
              {section.negatives.length === 0 ? (
                <p className="muted diff-col-empty">No negative changes detected.</p>
              ) : (
                section.negatives.map((text, i) => (
                  <div key={i} className="diff-item diff-item-negative">
                    <span className="diff-item-icon">↓</span>
                    <span>{text}</span>
                  </div>
                ))
              )}
            </div>
          </div>
        </>
      ) : (
        <p className="muted">No material changes detected in this section.</p>
      )}
    </section>
  )
}
