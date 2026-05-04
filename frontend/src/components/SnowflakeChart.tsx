import { memo, useId } from 'react'
import type { SnowflakeScores } from '../types/stock'
import { Shimmer } from './SkeletonReport'

interface SnowflakeChartProps {
  scores: SnowflakeScores | null
  loaded: boolean
  size?: number
}

const axes = [
  ['value', 'Value', 'Trades at a discount to sector medians'],
  ['growth', 'Growth', 'Revenue and earnings trajectory'],
  ['health', 'Health', 'Balance sheet and margin durability'],
  ['momentum', 'Momentum', 'Price and estimate trend quality'],
  ['smart_money', 'Smart Money', 'Institutional and insider signal'],
] as const

function point(center: number, radius: number, index: number) {
  const angle = -Math.PI / 2 + (index * 2 * Math.PI) / 5
  return [center + radius * Math.cos(angle), center + radius * Math.sin(angle)]
}

function SnowflakeChart({ scores, loaded, size = 280 }: SnowflakeChartProps) {
  const titleId = useId()
  const center = size / 2
  const radius = size * 0.35

  if (!loaded || !scores) {
    return (
      <div className="section-card chart-wrap">
        <Shimmer width={size} height={size} />
      </div>
    )
  }

  const values = axes.map(([key]) => Math.max(0, Math.min(10, scores[key])))
  const avg = values.reduce((sum, value) => sum + value, 0) / values.length
  const color = avg > 7 ? '#16a34a' : avg < 5 ? '#d97706' : '#0ea5e9'
  const outer = axes.map((_, index) => point(center, radius, index))
  const inner = values.map((value, index) => point(center, (radius * value) / 10, index))
  const path = inner.map(([x, y]) => `${x},${y}`).join(' ')

  return (
    <section className="section-card chart-wrap">
      <h2 className="section-title">Snowflake Score</h2>
      <svg role="img" aria-labelledby={titleId} width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <title id={titleId}>Five-axis stock quality score</title>
        <desc>Scores for value, growth, health, momentum, and smart money on a zero to ten scale.</desc>
        <polygon points={outer.map(([x, y]) => `${x},${y}`).join(' ')} fill="none" stroke="#cbd5e1" />
        {outer.map(([x, y], index) => (
          <line key={axes[index][0]} x1={center} y1={center} x2={x} y2={y} stroke="#e2e8f0" />
        ))}
        <polygon points={path} fill={color} fillOpacity="0.3" stroke={color} strokeWidth="2" />
        {inner.map(([x, y], index) => (
          <g key={axes[index][0]}>
            <circle cx={x} cy={y} r="5" fill={color}>
              <title>{`${axes[index][1]}: ${values[index].toFixed(1)}/10 - ${axes[index][2]}`}</title>
            </circle>
          </g>
        ))}
        {outer.map(([x, y], index) => (
          <text
            key={`${axes[index][0]}-label`}
            x={x}
            y={y}
            textAnchor="middle"
            dominantBaseline="middle"
            fontSize="11"
            fill="#475569"
          >
            <tspan x={x} dy="-0.25em">{axes[index][1]}</tspan>
            <tspan x={x} dy="1.2em">{values[index].toFixed(1)}</tspan>
          </text>
        ))}
      </svg>
      <div className="score-bars">
        {axes.map(([key, label], index) => (
          <div className="score-bar" key={key}>
            <span>{label}</span>
            <span className="bar-track"><span className="bar-fill" style={{ width: `${values[index] * 10}%`, background: color }} /></span>
            <strong>{values[index].toFixed(1)}</strong>
          </div>
        ))}
      </div>
      <details style={{ marginTop: 12 }}>
        <summary style={{ cursor: 'pointer', fontSize: 12, color: '#64748b', userSelect: 'none' }}>
          How this score is calculated ▸
        </summary>
        <div style={{ fontSize: 12, color: '#475569', marginTop: 8, lineHeight: 1.7, paddingLeft: 4 }}>
          <p style={{ margin: '0 0 6px' }}>
            <strong>Total score (0–100)</strong> = sum of the 5 dimensions × 2.
            {' '}Current total: <strong style={{ color }}>{(values.reduce((s, v) => s + v, 0) * 2).toFixed(0)}</strong>
          </p>
          <ul style={{ margin: 0, paddingLeft: 16 }}>
            <li><strong>Value:</strong> P/E and EV/EBITDA vs sector — lower multiples score higher</li>
            <li><strong>Growth:</strong> TTM revenue growth year-over-year</li>
            <li><strong>Health:</strong> Balance sheet strength — lower Debt/Equity scores higher</li>
            <li><strong>Momentum:</strong> Latest price vs 52-week high and 200-day moving average</li>
            <li><strong>Smart Money:</strong> Insider buying clusters and institutional fund signals</li>
          </ul>
          <p style={{ margin: '6px 0 0', color: '#94a3b8' }}>
            <span style={{ color: '#16a34a', fontWeight: 600 }}>≥ 70</span> Strong ·{' '}
            <span style={{ color: '#0ea5e9', fontWeight: 600 }}>50–69</span> Neutral ·{' '}
            <span style={{ color: '#d97706', fontWeight: 600 }}>{'< 50'}</span> Weak
          </p>
        </div>
      </details>
    </section>
  )
}

export default memo(SnowflakeChart)
