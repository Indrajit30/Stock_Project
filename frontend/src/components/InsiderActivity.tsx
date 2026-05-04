import { Bell, ShieldCheck } from 'lucide-react'
import { formatCurrency } from '../lib/format'
import type { InsiderCluster } from '../types/stock'
import { Shimmer } from './SkeletonReport'

export default function InsiderActivity({ cluster, loaded }: { cluster: InsiderCluster | null; loaded: boolean }) {
  if (!loaded) {
    return <section className="section-card"><h2 className="section-title">Insider Activity</h2><Shimmer height={142} /></section>
  }

  if (!cluster) {
    return (
      <section className="section-card">
        <h2 className="section-title"><ShieldCheck size={18} /> Insider Activity</h2>
        <p className="muted">No unusual insider buying activity in the last 30 days.</p>
      </section>
    )
  }

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
