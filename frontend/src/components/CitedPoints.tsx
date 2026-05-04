import { AlertTriangle, CheckCircle2, ExternalLink } from 'lucide-react'
import type { CitedPoint } from '../types/stock'
import { Shimmer } from './SkeletonReport'

export function CitationBadge({ source, url }: { source: string; url: string | null }) {
  if (!url) {
    return <span className="citation-badge">{source} (source on file)</span>
  }
  return (
    <a className="citation-badge" href={url} target="_blank" rel="noreferrer" title={source}>
      {source} <ExternalLink size={11} />
    </a>
  )
}

export default function CitedPoints({ points, type, loaded }: { points: CitedPoint[]; type: 'bull' | 'risk'; loaded: boolean }) {
  const isBull = type === 'bull'
  return (
    <section className="section-card">
      <h2 className="section-title">
        {isBull ? <CheckCircle2 color="#16a34a" size={18} /> : <AlertTriangle color="#dc2626" size={18} />}
        {isBull ? 'Bull Case' : 'Risk Factors'}
      </h2>
      {!loaded ? (
        <div className="cited-list">
          <Shimmer height={38} />
          <Shimmer width="86%" height={38} />
          <Shimmer width="92%" height={38} />
        </div>
      ) : (
        <div className="cited-list">
          {points.map((point) => (
            <div className="cited-point" key={`${point.source}-${point.text}`}>
              <span className={`point-dot ${isBull ? '' : 'risk-dot'}`} />
              <div>
                <div style={{ fontSize: 13, lineHeight: 1.6 }}>{point.text}</div>
                <CitationBadge source={point.source} url={point.source_url} />
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}
