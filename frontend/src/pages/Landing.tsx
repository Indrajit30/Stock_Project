import { ArrowRight, BadgeCheck, Clock3, FileSearch } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import SearchBox from '../components/SearchBox'

const features = [
  ['Citation-honest reports', 'Every number links to the exact SEC filing it came from', BadgeCheck],
  ['15-second analysis', 'Pre-computed nightly for top 50 tickers', Clock3],
  ['Retail + Pro modes', 'Plain English verdict or full analyst note', FileSearch],
] as const

export default function Landing() {
  const navigate = useNavigate()

  return (
    <div className="page-frame">
      <section className="landing-hero">
        <div className="landing-panel">
          <h1>Stock research that takes seconds, not hours</h1>
          <p className="landing-subtext">
            AI-powered analysis with citations from SEC filings - for retail and professional investors.
          </p>
          <SearchBox large placeholder="Try AAPL, NVDA, TSLA..." />
          <div className="ticker-pills">
            {['AAPL', 'NVDA', 'MSFT'].map((ticker) => (
              <button key={ticker} type="button" className="ticker-pill" onClick={() => navigate(`/stock/${ticker}`)}>
                {ticker}
              </button>
            ))}
          </div>
        </div>
      </section>
      <section className="feature-grid">
        {features.map(([title, copy, Icon]) => (
          <article className="feature-card" key={title}>
            <Icon size={22} color="#0ea5e9" />
            <h2>{title}</h2>
            <p className="muted">{copy}</p>
          </article>
        ))}
      </section>
      <section className="section-card" style={{ marginTop: 16 }}>
        <h2 className="section-title">How it works</h2>
        <p className="muted" style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
          Search a ticker <ArrowRight size={15} /> AI reads the filings <ArrowRight size={15} /> Get a cited verdict
        </p>
      </section>
    </div>
  )
}
