import { useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { api } from '../lib/api'
import { formatCurrency, formatPercent, formatRatio } from '../lib/format'
import type { PeerComparisonRow } from '../types/stock'

type SortKey = keyof Pick<
  PeerComparisonRow,
  'ticker' | 'market_cap' | 'pe_ratio' | 'ev_ebitda' | 'gross_margin' | 'revenue_growth_yoy' | 'net_margin' | 'debt_to_equity' | 'score'
>

const columns: { key: SortKey; label: string; render: (row: PeerComparisonRow) => string }[] = [
  { key: 'ticker', label: 'Company', render: (row) => `${row.company_name} (${row.ticker})` },
  { key: 'market_cap', label: 'Mkt Cap', render: (row) => formatCurrency(row.market_cap) },
  { key: 'pe_ratio', label: 'P/E (TTM)', render: (row) => formatRatio(row.pe_ratio) },
  { key: 'ev_ebitda', label: 'EV/EBITDA', render: (row) => formatRatio(row.ev_ebitda) },
  { key: 'gross_margin', label: 'Gross Margin', render: (row) => formatPercent(row.gross_margin) },
  { key: 'revenue_growth_yoy', label: 'Rev Growth YoY', render: (row) => formatPercent(row.revenue_growth_yoy) },
  { key: 'net_margin', label: 'Net Margin', render: (row) => formatPercent(row.net_margin) },
  { key: 'debt_to_equity', label: 'Debt/Equity', render: (row) => (row.debt_to_equity == null ? '-' : row.debt_to_equity.toFixed(2)) },
  { key: 'score', label: 'Score', render: (row) => String(row.score) },
]

const COLORS = {
  subject: '#0ea5e9',
  peer: '#94a3b8',
  pe: '#0ea5e9',
  ev: '#8b5cf6',
  grossMargin: '#16a34a',
  netMargin: '#f59e0b',
  revGrowth: '#ec4899',
}

function pct(v: number | null | undefined): number | null {
  return v != null ? parseFloat((v * 100).toFixed(1)) : null
}

function billions(v: number | null | undefined): number | null {
  return v != null ? parseFloat((v / 1e9).toFixed(2)) : null
}

const TooltipFormatter = (value: number | null, name: string) => {
  if (value == null) return ['-', name]
  if (name.includes('%')) return [`${value}%`, name]
  if (name.includes('$B')) return [`$${value}B`, name]
  return [value, name]
}

export default function PeerComparison({ ticker: propTicker }: { ticker?: string }) {
  const params = useParams()
  const ticker = propTicker || params.ticker?.toUpperCase() || 'AAPL'
  const [sortKey, setSortKey] = useState<SortKey>('score')
  const [direction, setDirection] = useState<'asc' | 'desc'>('desc')

  const { data, isLoading, error } = useQuery({
    queryKey: ['peers', ticker],
    queryFn: () => api.getPeers(ticker),
  })

  const rows = useMemo(() => {
    const source = data?.peers || []
    return [...source].sort((a, b) => {
      const left = a[sortKey]
      const right = b[sortKey]
      const result = typeof left === 'string'
        ? String(left).localeCompare(String(right))
        : (left == null ? Number.NEGATIVE_INFINITY : Number(left)) - (right == null ? Number.NEGATIVE_INFINITY : Number(right))
      return direction === 'asc' ? result : -result
    })
  }, [data?.peers, direction, sortKey])

  const selectSort = (key: SortKey) => {
    if (key === sortKey) {
      setDirection((current) => (current === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortKey(key)
      setDirection('desc')
    }
  }

  // Chart data derived from rows (ordered by ticker so subject is consistent)
  const chartRows = useMemo(() => [...rows].sort((a, b) => {
    if (a.ticker === ticker) return -1
    if (b.ticker === ticker) return 1
    return a.ticker.localeCompare(b.ticker)
  }), [rows, ticker])

  const valuationData = chartRows.map(row => ({
    ticker: row.ticker,
    'P/E (TTM)': row.pe_ratio != null ? parseFloat(row.pe_ratio.toFixed(1)) : null,
    'EV/EBITDA': row.ev_ebitda != null ? parseFloat(row.ev_ebitda.toFixed(1)) : null,
  }))

  const profitabilityData = chartRows.map(row => ({
    ticker: row.ticker,
    'Gross Margin %': pct(row.gross_margin),
    'Net Margin %': pct(row.net_margin),
    'Rev Growth % YoY': pct(row.revenue_growth_yoy),
  }))

  const marketCapData = chartRows.map(row => ({
    ticker: row.ticker,
    'Mkt Cap ($B)': billions(row.market_cap),
  }))

  if (isLoading) return <section className="section-card">Loading peer comparison...</section>
  if (error || !data) return <section className="section-card">Peer comparison is not available yet.</section>

  return (
    <div style={{ display: 'grid', gap: 16 }}>
      {/* Header with period note */}
      <section className="section-card">
        <h2 className="section-title">
          Comparing {ticker} to {rows.length - 1} sector peers · {data.industry}
        </h2>
        <p style={{ fontSize: 12, color: '#64748b', margin: '4px 0 12px' }}>
          Income metrics (Revenue, Margins, P/E) are <strong>Trailing Twelve Months (TTM)</strong>.
          Balance sheet metrics (Debt/Equity) reflect the most recent quarterly filing.
        </p>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                {columns.map((column) => (
                  <th key={column.key} onClick={() => selectSort(column.key)}>
                    {column.label} {sortKey === column.key ? (direction === 'asc' ? '↑' : '↓') : ''}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.ticker} className={row.ticker === ticker ? 'subject-row' : undefined}>
                  {columns.map((column) => (
                    <td key={column.key}>
                      {column.key === 'score' ? (
                        <span className={`score-pill ${row.score >= 70 ? 'buy' : row.score >= 40 ? 'wait' : 'risk'}`}>
                          {column.render(row)}
                        </span>
                      ) : (
                        column.render(row)
                      )}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Valuation chart */}
      <section className="section-card">
        <h2 className="section-title">Valuation Comparison (TTM)</h2>
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={valuationData} margin={{ top: 4, right: 16, left: 0, bottom: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
            <XAxis dataKey="ticker" tick={{ fontSize: 12 }} />
            <YAxis tick={{ fontSize: 11 }} />
            <Tooltip formatter={TooltipFormatter} />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Bar dataKey="P/E (TTM)" fill={COLORS.pe} radius={[3, 3, 0, 0]}>
              {valuationData.map((entry) => (
                <Cell
                  key={entry.ticker}
                  fill={entry.ticker === ticker ? COLORS.pe : '#bae6fd'}
                />
              ))}
            </Bar>
            <Bar dataKey="EV/EBITDA" fill={COLORS.ev} radius={[3, 3, 0, 0]}>
              {valuationData.map((entry) => (
                <Cell
                  key={entry.ticker}
                  fill={entry.ticker === ticker ? COLORS.ev : '#ddd6fe'}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </section>

      {/* Profitability chart */}
      <section className="section-card">
        <h2 className="section-title">Profitability & Growth (TTM)</h2>
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={profitabilityData} margin={{ top: 4, right: 16, left: 0, bottom: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
            <XAxis dataKey="ticker" tick={{ fontSize: 12 }} />
            <YAxis tickFormatter={(v) => `${v}%`} tick={{ fontSize: 11 }} />
            <Tooltip formatter={TooltipFormatter} />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Bar dataKey="Gross Margin %" fill={COLORS.grossMargin} radius={[3, 3, 0, 0]}>
              {profitabilityData.map((entry) => (
                <Cell
                  key={entry.ticker}
                  fill={entry.ticker === ticker ? COLORS.grossMargin : '#bbf7d0'}
                />
              ))}
            </Bar>
            <Bar dataKey="Net Margin %" fill={COLORS.netMargin} radius={[3, 3, 0, 0]}>
              {profitabilityData.map((entry) => (
                <Cell
                  key={entry.ticker}
                  fill={entry.ticker === ticker ? COLORS.netMargin : '#fde68a'}
                />
              ))}
            </Bar>
            <Bar dataKey="Rev Growth % YoY" fill={COLORS.revGrowth} radius={[3, 3, 0, 0]}>
              {profitabilityData.map((entry) => (
                <Cell
                  key={entry.ticker}
                  fill={entry.ticker === ticker ? COLORS.revGrowth : '#fbcfe8'}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </section>

      {/* Market cap chart */}
      <section className="section-card">
        <h2 className="section-title">Market Capitalisation</h2>
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={marketCapData} margin={{ top: 4, right: 16, left: 0, bottom: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
            <XAxis dataKey="ticker" tick={{ fontSize: 12 }} />
            <YAxis tickFormatter={(v) => `$${v}B`} tick={{ fontSize: 11 }} />
            <Tooltip formatter={TooltipFormatter} />
            <Bar dataKey="Mkt Cap ($B)" radius={[3, 3, 0, 0]}>
              {marketCapData.map((entry) => (
                <Cell
                  key={entry.ticker}
                  fill={entry.ticker === ticker ? COLORS.subject : COLORS.peer}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
        <p style={{ fontSize: 11, color: '#94a3b8', marginTop: 4 }}>
          Darker bar = {ticker} (subject). Market cap = latest price × shares outstanding from SEC.
        </p>
      </section>

      {/* AI Narrative */}
      <section className="section-card">
        <h2 className="section-title">AI Narrative</h2>
        {data.narrative.map((point) => (
          <p key={point.text} className="muted">{point.text} <strong>{point.source}</strong></p>
        ))}
      </section>

      {/* Smart Money Activity */}
      <section className="section-card">
        <h2 className="section-title">Smart Money Activity</h2>
        {data.superinvestor_cluster ? (
          <>
            <p>
              {data.superinvestor_cluster.fund_count} funds clustered in {data.superinvestor_cluster.quarter}.
              Signal strength: {data.superinvestor_cluster.signal_strength}/10.
            </p>
            {data.superinvestor_cluster.funds.map((fund) => (
              <div className="trade-row" key={fund.name}>
                <strong>{fund.name}</strong>
                <span className="muted">{fund.change}, {fund.aum_percent}% of reported AUM</span>
              </div>
            ))}
          </>
        ) : (
          <p className="muted">No superinvestor clustering detected this quarter.</p>
        )}
      </section>
    </div>
  )
}
