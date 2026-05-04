import { Landmark } from 'lucide-react'
import type { CongressionalTrade } from '../types/stock'
import { Shimmer } from './SkeletonReport'

export default function CongressionalTrades({ trades, loaded }: { trades: CongressionalTrade[] | null; loaded: boolean }) {
  if (!loaded) {
    return <section className="section-card"><h2 className="section-title">Congressional Trades</h2><Shimmer height={142} /></section>
  }

  return (
    <section className="section-card">
      <h2 className="section-title"><Landmark size={18} /> Congressional Trading Activity</h2>
      {trades && trades.length > 0 ? (
        <>
          {trades.map((trade) => (
            <div className="trade-row" key={`${trade.politician_name}-${trade.trade_date}`}>
              <strong>
                {trade.politician_name} <span className={`badge ${trade.party.toLowerCase().startsWith('d') ? 'wait' : 'risk'}`}>{trade.party}</span>
              </strong>
              <span className="muted">{trade.transaction_type} {trade.amount_range} on {trade.trade_date}</span>
            </div>
          ))}
          <p className="muted" style={{ marginBottom: 0 }}>Disclosed per STOCK Act. 45-day reporting delay applies.</p>
        </>
      ) : (
        <p className="muted">No recent congressional trades reported for this ticker.</p>
      )}
    </section>
  )
}
