import * as Tabs from '@radix-ui/react-tabs'
import { useQueryClient } from '@tanstack/react-query'
import { lazy, Suspense, useEffect } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import CitedPoints from '../components/CitedPoints'
import HedgingDetector from '../components/HedgingDetector'
import InsiderActivity from '../components/InsiderActivity'
import KeyMetrics from '../components/KeyMetrics'
import ReasoningTrace from '../components/ReasoningTrace'
import SentimentPulse from '../components/SentimentPulse'
import SkeletonReport from '../components/SkeletonReport'
import SnowflakeChart from '../components/SnowflakeChart'
import VerdictBanner from '../components/VerdictBanner'
import { api } from '../lib/api'
import { useStockStream } from '../hooks/useStockStream'

const PeerComparison = lazy(() => import('./PeerComparison'))
const FilingDiff = lazy(() => import('../components/FilingDiff'))

export default function StockReport() {
  const { ticker: routeTicker } = useParams()
  const ticker = routeTicker?.toUpperCase() || null
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const tab = searchParams.get('tab') || 'report'
  const state = useStockStream(ticker)

  useEffect(() => {
    if (ticker) document.title = `${ticker} - AI Stock Research`
  }, [ticker])

  useEffect(() => {
    if (state.status === 'done' && ticker) {
      queryClient.prefetchQuery({
        queryKey: ['peers', ticker],
        queryFn: () => api.getPeers(ticker),
      })
    }
  }, [queryClient, state.status, ticker])

  if (!ticker) return <SkeletonReport />

  const setTab = (next: string) => {
    navigate(next === 'report' ? `/stock/${ticker}` : `/stock/${ticker}?tab=${next}`)
  }

  const displayName = state.company_name || state.verdict?.company_name || null

  return (
    <div className="page-frame">
      {(displayName || ticker) && (
        <div style={{ marginBottom: 16, borderBottom: '1px solid #e2e8f0', paddingBottom: 12 }}>
          <h1 style={{ fontSize: 22, fontWeight: 700, color: '#0f172a', margin: 0 }}>
            {displayName || ticker}
            {displayName && (
              <span style={{ fontSize: 15, fontWeight: 400, color: '#64748b', marginLeft: 8 }}>
                ({ticker})
              </span>
            )}
          </h1>
        </div>
      )}
      <Tabs.Root value={tab} onValueChange={setTab}>
        <Tabs.List className="tabs-row" aria-label="Stock report tabs">
          <Tabs.Trigger className="tab-button" value="report">Report</Tabs.Trigger>
          <Tabs.Trigger className="tab-button" value="peers">Peer Comparison</Tabs.Trigger>
          <Tabs.Trigger className="tab-button" value="diff">Filing Diff</Tabs.Trigger>
        </Tabs.List>
        <Tabs.Content value="report">
          <ReasoningTrace steps={state.reasoning_steps} visible={state.status === 'streaming' || state.status === 'connecting'} />
          {state.status === 'error' && !state.verdict ? (
            <section className="section-card" style={{ marginBottom: 16 }}>
              {state.error || `Having trouble loading ${ticker}. Check the backend terminal for details.`}
            </section>
          ) : null}
          <VerdictBanner
            loaded={state.verdict !== null}
            verdict={state.verdict?.verdict}
            confidence={state.verdict?.verdict_confidence}
            summary={state.verdict?.plain_english_summary}
          />
          <div className="report-grid" style={{ marginBottom: 16 }}>
            <SnowflakeChart scores={state.snowflake} loaded={state.snowflake !== null} />
            <KeyMetrics financials={state.financials} loaded={state.financials !== null} />
          </div>
          <div className="points-grid" style={{ marginBottom: 16 }}>
            <CitedPoints type="bull" loaded={state.verdict !== null} points={state.verdict?.three_bulls || []} />
            <CitedPoints type="risk" loaded={state.verdict !== null} points={state.verdict?.three_risks || []} />
          </div>
          <div style={{ marginBottom: 16 }}>
            <SentimentPulse sentiment={state.sentiment} loaded={state.sentiment !== null} />
          </div>
          <div style={{ marginBottom: 16 }}>
            <InsiderActivity
              cluster={state.insider_cluster}
              ownership={state.institutional_ownership}
              loaded={state.insider_cluster !== null || state.institutional_ownership !== null || state.status === 'done'}
            />
          </div>
          <HedgingDetector finding={state.verdict?.hedging_detector} loaded={state.verdict !== null} />
        </Tabs.Content>
        <Tabs.Content value="peers">
          <Suspense fallback={<section className="section-card">Loading peer comparison...</section>}>
            <PeerComparison ticker={ticker} />
          </Suspense>
        </Tabs.Content>
        <Tabs.Content value="diff">
          <Suspense fallback={<section className="section-card">Loading filing diff...</section>}>
            <FilingDiff diff={state.filing_diff} loaded={state.filing_diff !== null} />
          </Suspense>
        </Tabs.Content>
      </Tabs.Root>
    </div>
  )
}
