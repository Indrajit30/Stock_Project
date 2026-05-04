import { Bell, Building2, ShieldCheck } from 'lucide-react'
import { formatCurrency } from '../lib/format'
import type { InsiderCluster, InstitutionalOwnership } from '../types/stock'
import { Shimmer } from './SkeletonReport'

function InsiderClusterCard({ cluster }: { cluster: InsiderCluster }) {
  return (
    <section className="section-card">
      <h2 className="section-title"><Bell color="#d97706" size={18} /> Insider Cluster Detected</h2>
      <p>
        {cluster.insider_count} insiders bought {formatCurrency(cluster.total_value_usd)} around {cluster.cluster_date}.
      </p>
      <div className="confidence-track" style={{ marginBottom: 12 }}>
        <div className="confidence-fill" style={{ width: `${cluster.signal_strength * 100}%`, background: '#d97706' }} />
      </div>
      {cluster.insiders.map((trade) => (
        <div className="trade-row" key={`${trade.name}-${trade.trade_date}`}>
          <strong>{trade.name} <span className="badge wait">{trade.role}</span></strong>
          <span className="muted">
            {trade.shares.toLocaleString()} shares, {formatCurrency(trade.value_usd)} on {trade.trade_date}
            {trade.is_10b5_plan ? ' (10b5-1 plan)' : ''}
          </span>
        </div>
      ))}
    </section>
  )
}

function fmt(n: number | null, isPercent = false): string {
  if (n == null) return '—'
  if (isPercent) return `${(n * 100).toFixed(1)}%`
  if (n >= 1e12) return `$${(n / 1e12).toFixed(2)}T`
  if (n >= 1e9) return `$${(n / 1e9).toFixed(2)}B`
  if (n >= 1e6) return `$${(n / 1e6).toFixed(1)}M`
  return n.toLocaleString()
}

function InstitutionalOwnershipCard({ ownership }: { ownership: InstitutionalOwnership }) {
  const hasHolders = ownership.top_holders.length > 0
  const hasStakeholders = ownership.major_stakeholders.length > 0

  if (!hasHolders && !hasStakeholders) {
    return (
      <section className="section-card">
        <h2 className="section-title"><Building2 size={18} /> Institutional Ownership</h2>
        <p className="muted">No institutional ownership data available.</p>
      </section>
    )
  }

  return (
    <section className="section-card">
      <h2 className="section-title"><Building2 size={18} /> Institutional Ownership</h2>

      {(ownership.pct_institutional != null || ownership.pct_insider != null) && (
        <div style={{ display: 'flex', gap: 24, marginBottom: 16 }}>
          {ownership.pct_institutional != null && (
            <div>
              <div style={{ fontSize: 22, fontWeight: 700 }}>{(ownership.pct_institutional * 100).toFixed(1)}%</div>
              <div className="muted" style={{ fontSize: 12 }}>Held by institutions</div>
            </div>
          )}
          {ownership.pct_insider != null && (
            <div>
              <div style={{ fontSize: 22, fontWeight: 700 }}>{(ownership.pct_insider * 100).toFixed(1)}%</div>
              <div className="muted" style={{ fontSize: 12 }}>Held by insiders</div>
            </div>
          )}
        </div>
      )}

      {hasHolders && (
        <>
          <h3 style={{ fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 8 }}>Top Institutional Holders</h3>
          <div style={{ overflowX: 'auto', marginBottom: 16 }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ borderBottom: '1px solid #e5e7eb' }}>
                  <th style={{ textAlign: 'left', padding: '4px 8px', color: '#6b7280', fontWeight: 500 }}>Fund / Institution</th>
                  <th style={{ textAlign: 'right', padding: '4px 8px', color: '#6b7280', fontWeight: 500 }}>Shares</th>
                  <th style={{ textAlign: 'right', padding: '4px 8px', color: '#6b7280', fontWeight: 500 }}>Value</th>
                </tr>
              </thead>
              <tbody>
                {ownership.top_holders.map((h, i) => (
                  <tr key={i} style={{ borderBottom: '1px solid #f3f4f6' }}>
                    <td style={{ padding: '5px 8px', fontWeight: 500 }}>{h.name}</td>
                    <td style={{ padding: '5px 8px', textAlign: 'right', color: '#374151' }}>{h.shares >= 1e6 ? `${(h.shares / 1e6).toFixed(1)}M` : h.shares.toLocaleString()}</td>
                    <td style={{ padding: '5px 8px', textAlign: 'right', color: '#374151' }}>{fmt(h.value_usd)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

    </section>
  )
}

export default function InsiderActivity({
  cluster,
  ownership,
  loaded,
}: {
  cluster: InsiderCluster | null
  ownership: InstitutionalOwnership | null
  loaded: boolean
}) {
  if (!loaded) {
    return (
      <>
        <section className="section-card"><h2 className="section-title">Insider Activity</h2><Shimmer height={100} /></section>
        <section className="section-card"><h2 className="section-title">Institutional Ownership</h2><Shimmer height={160} /></section>
      </>
    )
  }

  return (
    <>
      {cluster ? (
        <InsiderClusterCard cluster={cluster} />
      ) : (
        <section className="section-card">
          <h2 className="section-title"><ShieldCheck size={18} /> Insider Activity</h2>
          <p className="muted">No unusual insider buying activity in the last 30 days.</p>
        </section>
      )}
      {ownership && <InstitutionalOwnershipCard ownership={ownership} />}
    </>
  )
}
