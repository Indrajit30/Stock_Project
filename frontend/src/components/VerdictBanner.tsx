import type { Verdict } from '../types/stock'
import { Shimmer } from './SkeletonReport'

interface VerdictBannerProps {
  verdict?: Verdict
  confidence?: number
  summary?: string
  loaded: boolean
}

const symbols: Record<Verdict, string> = {
  buy: '●',
  wait: '◐',
  avoid: 'x',
}

export default function VerdictBanner({ verdict, confidence = 0, summary, loaded }: VerdictBannerProps) {
  if (!loaded || !verdict) {
    return (
      <div className="verdict-banner">
        <Shimmer height={76} />
        <Shimmer height={76} />
      </div>
    )
  }

  const percent = Math.round(confidence * 100)

  return (
    <section
      className={`verdict-banner verdict-${verdict}`}
      aria-label={`Investment verdict: ${verdict.toUpperCase()} with ${percent}% confidence`}
    >
      <div>
        <span className={`verdict-pill ${verdict}`}>
          {symbols[verdict]} {verdict.toUpperCase()}
        </span>
        <div className="muted" style={{ marginTop: 8 }}>{percent}% confidence</div>
        <div className="confidence-track">
          <div className="confidence-fill" style={{ width: `${percent}%` }} />
        </div>
      </div>
      <div>
        <p style={{ margin: 0, fontSize: 16, lineHeight: 1.6 }}>{summary}</p>
        {confidence < 0.6 ? (
          <p className="muted" style={{ marginTop: 8 }}>
            Lower confidence - data was limited. Read the full analysis below.
          </p>
        ) : null}
      </div>
    </section>
  )
}
