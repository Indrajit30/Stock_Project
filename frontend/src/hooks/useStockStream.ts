import { useEffect, useState } from 'react'
import { API_URL } from '../lib/api'
import type { ReasoningStep, StreamState } from '../types/stock'

const INITIAL_STATE: StreamState = {
  financials: null,
  snowflake: null,
  sentiment: null,
  filing_diff: null,
  insider_cluster: null,
  congressional_trades: null,
  verdict: null,
  reasoning_steps: [],
  company_name: null,
  status: 'idle',
  error: null,
}

function updateReasoningStep(steps: ReasoningStep[], event: ReasoningStep) {
  const index = steps.findIndex((step) => step.step_number === event.step_number)
  if (index === -1) return [...steps, event]
  return steps.map((step, idx) => (idx === index ? { ...step, ...event } : step))
}

export function useStockStream(ticker: string | null) {
  const [state, setState] = useState<StreamState>(INITIAL_STATE)

  useEffect(() => {
    if (!ticker) {
      setState(INITIAL_STATE)
      return
    }

    setState({ ...INITIAL_STATE, status: 'connecting' })
    const url = `${API_URL}/api/stock/${ticker}/report/stream`
    const es = new EventSource(url)

    es.onopen = () => setState((current) => ({ ...current, status: 'streaming', error: null }))

    es.onmessage = (message) => {
      const event = JSON.parse(message.data)

      switch (event.event) {
        case 'section_start':
          if (event.company_name) {
            setState((current) => ({ ...current, company_name: event.company_name }))
          }
          break
        case 'data':
          if (event.section === 'verdict' && event.payload?.company_name) {
            setState((current) => ({ ...current, [event.section]: event.payload, company_name: event.payload.company_name }))
          } else {
            setState((current) => ({ ...current, [event.section]: event.payload }))
          }
          break
        case 'reasoning_step':
          setState((current) => ({
            ...current,
            reasoning_steps: updateReasoningStep(current.reasoning_steps, event),
          }))
          break
        case 'error':
          setState((current) => ({
            ...current,
            status: 'error',
            error: event.message || 'Report generation failed.',
          }))
          es.close()
          break
        case 'done':
          setState((current) => ({ ...current, status: 'done' }))
          es.close()
          break
        default:
          break
      }
    }

    es.onerror = () => {
      setState((current) => ({
        ...current,
        status: 'error',
        error: 'Connection lost. Retrying...',
      }))
    }

    return () => es.close()
  }, [ticker])

  return state
}
