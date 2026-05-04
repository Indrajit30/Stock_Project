import { ShieldAlert } from 'lucide-react'
import { Shimmer } from './SkeletonReport'

export default function HedgingDetector({ finding, loaded }: { finding?: string; loaded: boolean }) {
  return (
    <section className="section-card">
      <h2 className="section-title"><ShieldAlert size={18} /> Hedging Detector</h2>
      {loaded ? <p className="muted">{finding || 'No unusual hedging language detected in the analyzed transcript.'}</p> : <Shimmer height={60} />}
    </section>
  )
}
