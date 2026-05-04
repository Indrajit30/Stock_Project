import { CheckCircle2, Loader2, XCircle } from 'lucide-react'
import { useEffect, useState } from 'react'
import type { ReasoningStep } from '../types/stock'

export default function ReasoningTrace({ steps, visible }: { steps: ReasoningStep[]; visible: boolean }) {
  const [expanded, setExpanded] = useState(true)

  useEffect(() => {
    if (!visible && steps.length > 0) {
      const timer = window.setTimeout(() => setExpanded(false), 2000)
      return () => window.clearTimeout(timer)
    }
    setExpanded(true)
  }, [visible, steps.length])

  if (steps.length === 0) return null

  const done = steps.filter((step) => step.status === 'done').length
  const totalDuration = steps.reduce((sum, step) => sum + (step.duration_ms || 0), 0) / 1000

  return (
    <section className="section-card reasoning-panel">
      <button type="button" className="recent-item" onClick={() => setExpanded((current) => !current)}>
        <strong>{visible ? 'AI Agent Working...' : `Analysis complete - ${done} steps, ${totalDuration.toFixed(1)}s total`}</strong>
        <span className="muted">{expanded ? 'Hide' : 'Show analysis steps'}</span>
      </button>
      {expanded ? (
        <div>
          {steps.map((step) => (
            <div className="reasoning-step" key={step.step_number}>
              {step.status === 'running' ? <Loader2 className="spin" size={18} /> : null}
              {step.status === 'done' ? <CheckCircle2 color="#16a34a" size={18} /> : null}
              {step.status === 'error' ? <XCircle color="#dc2626" size={18} /> : null}
              <div>
                <strong>{step.title}</strong>
                {step.finding ? <div className="muted" style={{ fontStyle: 'italic', marginTop: 3 }}>{step.finding}</div> : null}
              </div>
              <span className="muted">{step.duration_ms ? `${(step.duration_ms / 1000).toFixed(1)}s` : ''}</span>
            </div>
          ))}
        </div>
      ) : null}
    </section>
  )
}
