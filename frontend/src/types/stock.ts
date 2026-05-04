export type Verdict = 'buy' | 'wait' | 'avoid'

export interface CitedPoint {
  text: string
  source: string
  source_url: string | null
}

export interface SnowflakeScores {
  value: number
  growth: number
  health: number
  momentum: number
  smart_money: number
}

export interface FinancialSnapshot {
  revenue_ttm: number | null
  net_income_ttm: number | null
  gross_margin: number | null
  pe_ratio: number | null
  ev_ebitda: number | null
  debt_to_equity: number | null
  market_cap: number | null
  sector: string | null
  industry: string | null
  revenue_growth_yoy: number | null
}

export interface PeerComparisonRow {
  ticker: string
  company_name: string
  market_cap: number | null
  pe_ratio: number | null
  ev_ebitda: number | null
  gross_margin: number | null
  revenue_growth_yoy: number | null
  net_margin: number | null
  debt_to_equity: number | null
  score: number
  snowflake_scores: SnowflakeScores
}

export interface InsiderTrade {
  name: string
  role: string
  shares: number
  value_usd: number
  trade_date: string
  is_10b5_plan: boolean
}

export interface InsiderCluster {
  ticker: string
  cluster_date: string
  total_value_usd: number
  insider_count: number
  insiders: InsiderTrade[]
  signal_strength: number
}

export interface SentimentPost {
  subreddit: string
  title: string
  score: number
  sentiment: number
  url: string
}

export interface SentimentPulse {
  ticker: string
  reddit_score: number
  reddit_mention_count: number
  top_posts: SentimentPost[]
  updated_at: string
}

export interface DiffLine {
  type: 'add' | 'delete' | 'context'
  text: string
}

export interface FilingDiffSection {
  section_name: string
  summary: string
  additions: string[]
  deletions: string[]
}

export interface FilingDiff {
  ticker: string
  filing_type: string
  current_period: string
  prior_period: string
  changed_sections: FilingDiffSection[]
}

export interface VerdictPayload {
  ticker: string
  company_name: string
  verdict: Verdict
  verdict_confidence: number
  plain_english_summary: string
  three_bulls: CitedPoint[]
  three_risks: CitedPoint[]
  hedging_detector?: string
}

export interface StockReport extends VerdictPayload {
  snowflake_scores: SnowflakeScores
  financials: FinancialSnapshot
  generated_at: string
}

export interface PeerComparisonResponse {
  ticker: string
  industry: string
  peers: PeerComparisonRow[]
  narrative: CitedPoint[]
  superinvestor_cluster: {
    quarter: string
    fund_count: number
    signal_strength: number
    funds: { name: string; aum_percent: number; change: string }[]
  } | null
}

export interface ReasoningStep {
  step_number: number
  title: string
  status: 'running' | 'done' | 'error'
  finding: string | null
  duration_ms?: number
}

export interface InstitutionalHolder {
  name: string
  shares: number
  value_usd: number | null
  pct_outstanding: number | null
  reported_date: string | null
}

export interface MajorStakeholder {
  name: string
  filing_type: string
  filed_date: string
  is_activist: boolean
}

export interface InstitutionalOwnership {
  ticker: string
  pct_institutional: number | null
  pct_insider: number | null
  top_holders: InstitutionalHolder[]
  major_stakeholders: MajorStakeholder[]
  updated_at: string
}

export interface StreamState {
  financials: FinancialSnapshot | null
  snowflake: SnowflakeScores | null
  sentiment: SentimentPulse | null
  filing_diff: FilingDiff | null
  insider_cluster: InsiderCluster | null
  institutional_ownership: InstitutionalOwnership | null
  verdict: VerdictPayload | null
  reasoning_steps: ReasoningStep[]
  company_name: string | null
  status: 'idle' | 'connecting' | 'streaming' | 'done' | 'error'
  error: string | null
}
