import type { SentimentPulse as SentimentPulseType } from '../types/stock'
import { Shimmer } from './SkeletonReport'

export default function SentimentPulse({ sentiment, loaded }: { sentiment: SentimentPulseType | null; loaded: boolean }) {
  if (!loaded || !sentiment) {
    return (
      <section className="section-card">
        <h2 className="section-title">Reddit Sentiment</h2>
        <Shimmer height={170} />
      </section>
    )
  }

  const score = Math.max(-1, Math.min(1, sentiment.reddit_score))
  const angle = -90 + ((score + 1) / 2) * 180
  const label = score > 0.3 ? 'Bullish' : score < -0.3 ? 'Bearish' : 'Neutral'

  return (
    <section className="section-card">
      <h2 className="section-title">Reddit Sentiment</h2>
      <div className="sentiment-gauge">
        <svg viewBox="0 0 240 130" role="img" aria-label={`Reddit sentiment is ${label}`}>
          <path d="M30 115 A90 90 0 0 1 210 115" fill="none" stroke="#e2e8f0" strokeWidth="22" />
          <path d="M30 115 A90 90 0 0 1 86 32" fill="none" stroke="#dc2626" strokeWidth="22" />
          <path d="M86 32 A90 90 0 0 1 154 32" fill="none" stroke="#94a3b8" strokeWidth="22" />
          <path d="M154 32 A90 90 0 0 1 210 115" fill="none" stroke="#16a34a" strokeWidth="22" />
          <line x1="120" y1="115" x2="120" y2="38" stroke="#0f172a" strokeWidth="4" transform={`rotate(${angle} 120 115)`} />
          <circle cx="120" cy="115" r="7" fill="#0ea5e9" />
        </svg>
      </div>
      <p style={{ textAlign: 'center' }}>
        <strong>{label}</strong> - {sentiment.reddit_mention_count.toLocaleString()} mentions in the past week
      </p>
      {sentiment.top_posts.map((post) => (
        <a className="post-row" href={post.url} target="_blank" rel="noreferrer" key={post.url}>
          <span><span className="badge">{post.subreddit}</span> {post.title.slice(0, 60)}</span>
          <span className="muted">{post.score.toLocaleString()} arrows</span>
        </a>
      ))}
      <p className="muted" style={{ marginBottom: 0 }}>Sentiment from public Reddit posts. Not a trading signal.</p>
    </section>
  )
}
