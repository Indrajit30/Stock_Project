import { formatCurrency, formatPercent, formatRatio } from '../lib/format'
import type { FinancialSnapshot } from '../types/stock'
import { Shimmer } from './SkeletonReport'

export default function KeyMetrics({ financials, loaded }: { financials: FinancialSnapshot | null; loaded: boolean }) {
  if (!loaded || !financials) {
    return (
      <section className="section-card">
        <h2 className="section-title">Key Metrics</h2>
        <div className="metric-grid">
          {Array.from({ length: 8 }, (_, index) => <Shimmer key={index} height={56} />)}
        </div>
      </section>
    )
  }

  const metrics = [
    ['Revenue TTM', formatCurrency(financials.revenue_ttm)],
    ['Net Income TTM', formatCurrency(financials.net_income_ttm)],
    ['Gross Margin (TTM)', formatPercent(financials.gross_margin)],
    ['P/E Ratio (TTM)', formatRatio(financials.pe_ratio)],
    ['EV/EBITDA (TTM)', formatRatio(financials.ev_ebitda)],
    ['Debt/Equity (Latest Qtr)', financials.debt_to_equity == null ? '-' : financials.debt_to_equity.toFixed(2)],
    ['Market Cap', formatCurrency(financials.market_cap)],
    ['Industry', financials.industry || '-'],
  ]

  return (
    <section className="section-card">
      <h2 className="section-title">Key Metrics</h2>
      <div className="metric-grid">
        {metrics.map(([label, value]) => (
          <div className="metric" key={label}>
            <span className="metric-label">{label}</span>
            <span className="metric-value">{value}</span>
          </div>
        ))}
      </div>
      <p style={{ fontSize: 11, color: '#94a3b8', marginTop: 8 }}>
        TTM = Trailing Twelve Months (last 4 quarters). Balance sheet reflects latest quarterly filing.
        Market cap = latest price × shares outstanding from SEC.
      </p>
    </section>
  )
}
