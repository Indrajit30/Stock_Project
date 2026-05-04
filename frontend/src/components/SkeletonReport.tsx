import type { ReactNode } from 'react'

export function Shimmer({ height = 16, width = '100%' }: { height?: number; width?: number | string }) {
  return <div className="shimmer" style={{ height, width }} />
}

export function SkeletonSection({ loaded, children, height = 180 }: { loaded: boolean; children: ReactNode; height?: number }) {
  if (!loaded) {
    return <div className="section-card"><Shimmer height={height} /></div>
  }
  return <div style={{ animation: 'enter 0.2s ease both' }}>{children}</div>
}

export default function SkeletonReport() {
  return (
    <div className="page-frame" aria-label="Loading stock report">
      <div className="section-card" style={{ marginBottom: 16 }}>
        <Shimmer width={180} height={22} />
        <div style={{ height: 12 }} />
        <Shimmer height={58} />
      </div>
      <div className="report-grid" style={{ marginBottom: 16 }}>
        <div className="section-card"><Shimmer height={260} /></div>
        <div className="section-card"><Shimmer height={260} /></div>
      </div>
      <div className="points-grid">
        <div className="section-card"><Shimmer height={190} /></div>
        <div className="section-card"><Shimmer height={190} /></div>
      </div>
    </div>
  )
}
