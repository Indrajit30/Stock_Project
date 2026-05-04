# Person 3 — React Frontend, UI/UX & Visualizations
## Claude Code Prompt Roadmap

> Feed each section to Claude Code in order. Complete one before starting the next.
> Your job: build the interface that makes the app feel magical. Speed perception IS your job.

---

## CONTEXT (paste this at the start of every Claude Code session)

```
We are building an AI stock research web app. I own the React frontend.

Stack:
- React 18 + TypeScript + Vite
- Tailwind CSS for styling
- Vercel AI SDK (useChat, streamObject hooks) for SSE consumption
- React Query (TanStack) for data fetching and caching
- Recharts for charts
- React PDF / jspdf for client-side PDF preview
- Lucide React for icons

Backend API is on port 8000 (use VITE_API_URL env var, default http://localhost:8000).
Mock server is on port 8001 — start with mock until backend is ready.

All data types come from shared/schemas.py (Pydantic). I need TypeScript equivalents.
Person 2 (agent) owns the SSE streaming. I consume it using EventSource.

SSE event protocol from Person 2:
  data: {"event": "section_start", "section": "overview", "ticker": "AAPL"}
  data: {"event": "data", "section": "financials", "payload": {...}}
  data: {"event": "data", "section": "snowflake", "payload": {...}}
  data: {"event": "data", "section": "sentiment", "payload": {...}}
  data: {"event": "data", "section": "filing_diff", "payload": {...}}
  data: {"event": "data", "section": "insider_cluster", "payload": {...}}
  data: {"event": "data", "section": "congressional_trades", "payload": [...]}
  data: {"event": "reasoning_step", "step_number": 1, "title": "...", "status": "running"|"done"}
  data: {"event": "data", "section": "verdict", "payload": {...}}
  data: {"event": "done", "ticker": "AAPL", "generated_at": "..."}

CRITICAL UX RULE: Users see content within 2 seconds. The skeleton UI with shimmer
placeholders renders immediately. Each section fills in as SSE events arrive.
Never show a blank white screen while loading.
```

---

## PHASE 1 — Project setup & design system (Day 1–2)

### Prompt 1.1 — Vite + TypeScript scaffold
```
Create a new React + TypeScript + Vite project for our stock research app.

Run: npm create vite@latest frontend -- --template react-ts
Then: cd frontend && npm install

Install these packages:
  npm install @tanstack/react-query recharts lucide-react
  npm install tailwindcss @tailwindcss/vite
  npm install clsx tailwind-merge
  npm install jspdf html2canvas
  npm install date-fns
  npm install @radix-ui/react-tabs @radix-ui/react-tooltip @radix-ui/react-dialog

Configure tailwind.config.ts with this custom color palette:
  colors:
    brand:
      50: '#f0f9ff'
      500: '#0ea5e9'  (primary blue)
      900: '#0c4a6e'
    verdict:
      buy: '#16a34a'      (green)
      wait: '#d97706'     (amber)
      avoid: '#dc2626'    (red)
    surface: '#f8fafc'
    border: '#e2e8f0'

Create src/types/stock.ts with TypeScript interfaces matching shared/schemas.py:
  interface StockReport { ticker, company_name, verdict, verdict_confidence,
    plain_english_summary, three_bulls, three_risks, snowflake_scores, financials, generated_at }
  interface CitedPoint { text, source, source_url }
  interface SnowflakeScores { value, growth, health, momentum, smart_money }
  interface FinancialSnapshot { revenue_ttm, net_income_ttm, gross_margin, pe_ratio,
    ev_ebitda, debt_to_equity, market_cap, sector, industry }
  interface PeerComparisonRow { ticker, company_name, market_cap, pe_ratio, ev_ebitda,
    gross_margin, revenue_growth_yoy, net_margin, debt_to_equity, snowflake_scores }
  interface InsiderCluster { ticker, cluster_date, total_value_usd, insider_count, insiders, signal_strength }
  interface SentimentPulse { ticker, reddit_score, reddit_mention_count, top_posts, updated_at }
  interface FilingDiff { ticker, filing_type, current_period, prior_period, changed_sections }

Create src/lib/api.ts:
  const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8001'  // default to mock
  export const api = { ... }  // typed fetch wrappers for all endpoints

Create .env.local: VITE_API_URL=http://localhost:8001 (mock to start)
```

### Prompt 1.2 — Layout & navigation
```
Create the app shell in src/App.tsx and src/components/Layout.tsx.

App has a single-page layout with:

TOP NAV BAR (fixed, 56px tall):
  - Left: App logo "StockAI" in brand-500 color + tagline "Research in seconds"
  - Center: Search bar (large, 400px wide on desktop) with placeholder "Search ticker e.g. AAPL"
    - On Enter or click: navigate to /stock/{TICKER}
    - Show autocomplete dropdown with recent searches (stored in localStorage)
  - Right: "Export" button (shows when on a stock page) + GitHub link icon

MAIN CONTENT AREA (below nav, full width):
  - Router: 
    / → Landing page (Prompt 1.3)
    /stock/:ticker → Stock Report page (Prompt 2.1)
    /stock/:ticker?tab=peers → Peer Comparison tab (Prompt 3.1)

Use React Router v6: npm install react-router-dom

The nav search bar should be the primary entry point. When user types a ticker and hits Enter,
immediately navigate to /stock/AAPL and start the SSE stream — don't wait for a button click.

Add a keyboard shortcut: pressing "/" anywhere focuses the search bar (like GitHub).
```

### Prompt 1.3 — Landing page
```
Create src/pages/Landing.tsx — the home page when no ticker is selected.

Design a clean, minimal landing page:

HERO SECTION (centered, 60vh):
  Heading: "Stock research that takes seconds, not hours"
  Subtext: "AI-powered analysis with citations from SEC filings — for retail and professional investors"
  Large search bar (same as nav, 600px wide): placeholder "Try AAPL, NVDA, TSLA..."
  Three example ticker pills below: [AAPL] [NVDA] [MSFT] — clicking navigates to that stock

FEATURE HIGHLIGHTS (3-column grid, below hero):
  Card 1: "Citation-honest reports" — "Every number links to the exact SEC filing it came from"
  Card 2: "15-second analysis" — "Pre-computed nightly for top 50 tickers"
  Card 3: "Retail + Pro modes" — "Plain English verdict or full analyst note"

HOW IT WORKS (3 steps, horizontal):
  1. Search a ticker → 2. AI reads the filings → 3. Get a cited verdict

Keep it minimal. White background, clean typography, brand-500 accents. No stock photos.
The landing page should load in < 100ms (pure static, no API calls).
```

---

## PHASE 2 — Stock report page (Day 2–5)

### Prompt 2.1 — SSE streaming hook
```
Create src/hooks/useStockStream.ts — the core hook that consumes the SSE stream.

This hook is the most important piece of frontend code. It drives the entire report page.

interface StreamState {
  financials: FinancialSnapshot | null
  snowflake: SnowflakeScores | null
  sentiment: SentimentPulse | null
  filing_diff: FilingDiff | null
  insider_cluster: InsiderCluster | null
  congressional_trades: any[] | null
  verdict: VerdictPayload | null
  reasoning_steps: ReasoningStep[]
  status: 'idle' | 'connecting' | 'streaming' | 'done' | 'error'
  error: string | null
}

interface ReasoningStep {
  step_number: number
  title: string
  status: 'running' | 'done' | 'error'
  finding: string | null
}

export function useStockStream(ticker: string | null) {
  const [state, setState] = useState<StreamState>(INITIAL_STATE)
  
  useEffect(() => {
    if (!ticker) return
    
    setState(INITIAL_STATE)  // reset on new ticker
    
    const url = `${API_URL}/api/stock/${ticker}/report/stream`
    const es = new EventSource(url)
    
    es.onopen = () => setState(s => ({ ...s, status: 'streaming' }))
    
    es.onmessage = (e) => {
      const event = JSON.parse(e.data)
      
      switch(event.event) {
        case 'data':
          setState(s => ({ ...s, [event.section]: event.payload }))
          break
        case 'reasoning_step':
          setState(s => ({
            ...s,
            reasoning_steps: updateReasoningStep(s.reasoning_steps, event)
          }))
          break
        case 'done':
          setState(s => ({ ...s, status: 'done' }))
          es.close()
          break
      }
    }
    
    es.onerror = () => {
      setState(s => ({ ...s, status: 'error', error: 'Connection lost. Retrying...' }))
      // EventSource auto-retries — don't close it
    }
    
    return () => es.close()
  }, [ticker])
  
  return state
}

Note: EventSource in browsers handles reconnection automatically — don't add manual retry logic.
The status 'error' is for display only; EventSource will keep trying.
```

### Prompt 2.2 — Skeleton loading UI
```
Create src/components/SkeletonReport.tsx — the shimmer skeleton shown while streaming.

CRITICAL: This component renders IMMEDIATELY when a ticker is searched.
The user sees this within 50ms. Sections fill in as SSE events arrive.

Design skeleton layout matching the final report structure:

  ┌─────────────────────────────────────────────────────┐
  │  [████████████] AAPL    ████████████████████        │  ← company name + shimmer
  │  [██████████████████████████████████]               │  ← verdict badge shimmer  
  │  ████████████████████████████████████████           │  ← summary text shimmer
  ├──────────────┬──────────────────────────────────────┤
  │  [Snowflake] │  Key Metrics                         │
  │  shimmer     │  P/E: ████   EV/EBITDA: ████        │
  │  pentagon    │  Gross Margin: ████  Revenue: ████   │
  ├──────────────┴──────────────────────────────────────┤
  │  Bull Case          │  Bear Case                    │
  │  • ██████████████   │  • ██████████████             │
  │  • ██████████████   │  • ██████████████             │
  │  • ██████████████   │  • ██████████████             │
  └─────────────────────────────────────────────────────┘

Shimmer animation: CSS keyframe animation that slides a light gradient left-to-right
over gray placeholder rects. Duration: 1.5s, infinite.

@keyframes shimmer {
  0% { background-position: -200% 0; }
  100% { background-position: 200% 0; }
}
.shimmer {
  background: linear-gradient(90deg, #f0f0f0 25%, #e0e0e0 50%, #f0f0f0 75%);
  background-size: 200% 100%;
  animation: shimmer 1.5s infinite;
  border-radius: 4px;
}

Build SkeletonSection component:
  - Accepts: loaded: boolean, children: ReactNode
  - If loaded=false: renders shimmer rect of similar dimensions
  - If loaded=true: fades in children with a 200ms ease transition

Use this for every section: skeleton shows until SSE event for that section arrives.
```

### Prompt 2.3 — Verdict banner component
```
Create src/components/VerdictBanner.tsx

This is the most prominent element — the AI's BUY/WAIT/AVOID verdict.

Props: verdict: 'buy'|'wait'|'avoid', confidence: number, summary: string, loaded: boolean

Design:
  - Full-width banner, 120px tall
  - Background color based on verdict:
    buy  → gradient from green-50 to white, left border 4px solid green-600
    wait → gradient from amber-50 to white, left border 4px solid amber-500
    avoid → gradient from red-50 to white, left border 4px solid red-600
  - Left side: Large verdict badge
    - buy  → green pill "● BUY" with confidence percentage below (e.g. "83% confidence")
    - wait → amber pill "◐ WAIT" 
    - avoid → red pill "✕ AVOID"
  - Right side: plain_english_summary text (16px, readable)
  - Confidence shown as a thin progress bar under the verdict badge

  When loaded=false: show SkeletonSection shimmer over the entire banner

Add a subtle entrance animation: slide in from top + fade in over 300ms when loaded transitions
false → true. Use CSS transitions, not a JS animation library.

IMPORTANT: The verdict text must be human-readable. If verdict_confidence < 0.6, add a
disclaimer: "Lower confidence — data was limited. Read the full analysis below."
```

### Prompt 2.4 — Snowflake visual score (Pentagon chart)
```
Create src/components/SnowflakeChart.tsx — the signature visual element.

This is the Simply Wall St-inspired pentagon chart. It's the most iconic visual
in the app and shows at a glance how a stock scores on 5 dimensions.

Props: scores: SnowflakeScores, loaded: boolean, size?: number (default 280)

Build using SVG (no external charting library — this is custom):

  Pentagon with 5 axes radiating from center:
    Top:         Value (score: 0-10)
    Upper-right: Growth
    Lower-right: Health  
    Lower-left:  Momentum
    Upper-left:  Smart Money

  Drawing:
    1. Calculate 5 outer pentagon points at radius=120 (max score)
    2. For each score, calculate inner point = score/10 * 120 from center
    3. Draw 5 axis lines from center to outer vertices (gray, thin)
    4. Draw outer pentagon border (light gray)
    5. Draw filled score polygon: connect 5 inner points, fill with brand-500 at 30% opacity,
       stroke brand-500 at full opacity, stroke-width 2
    6. Draw score dots at each inner point (filled circles, brand-500)
    7. Label each axis with name and score: "Value\n7.2" at outer vertex

  Color the filled polygon based on average score:
    avg > 7: green (good overall)
    avg 5-7: brand-500 blue (neutral)
    avg < 5: amber (below average)

  Add tooltip on hover over each axis dot:
    Shows: axis name, score, and 1-line explanation
    e.g. "Value: 7.2/10 — Trades at slight discount to sector median P/E"
    (The explanation text comes from the parent passing a scores_detail prop)

  When loaded=false: render a gray pentagon outline with shimmer
  When loaded=true: animate the fill from 0 to final score (300ms ease, draws in like a radar chart)

  Add below the pentagon: 5 small labeled score bars (horizontal) for accessibility:
    Value  ████████░░  7.2
    Growth ██████████  9.1
    etc.
```

### Prompt 2.5 — Bull/Bear cited points
```
Create src/components/CitedPoints.tsx

This renders the three bull points and three risk points, each with clickable source citations.

Props:
  points: CitedPoint[]
  type: 'bull' | 'risk'
  loaded: boolean

Design:
  - Card with header: "Bull Case" (green checkmark icon) or "Risk Factors" (red warning icon)
  - 3 items, each as a row:
    - Left: colored dot (green for bull, red for risk)
    - Text: the claim in plain English (13px, readable, line-height 1.6)
    - Below text: citation badge — small gray pill showing source name
      Clicking it opens source_url in a new tab
      e.g. [AAPL 10-Q Q3 2024 — MD&A Section ↗]
    - Hover on citation: tooltip shows fuller source description

  - Source badges should be subtle — they add trust without dominating the design
  - If source_url is null: show badge as non-clickable with "(source on file)" text

  Citation badge component:
    <CitationBadge source="AAPL 10-Q Q3 2024" url="https://sec.gov/..." />
    Style: 11px, bg-gray-100, text-gray-600, rounded-full, px-2 py-0.5
    On hover: bg-gray-200, cursor: pointer (if url exists)

  When loaded=false: show 3 shimmer rows of varying widths (to look like real text)
```

### Prompt 2.6 — Reasoning trace panel
```
Create src/components/ReasoningTrace.tsx — shows users the agent is working.

Props: steps: ReasoningStep[], visible: boolean

Design: Collapsible panel at the top of the report, visible while streaming.
Header: "AI Agent Working..." (animated dots) or "Analysis complete" (checkmark) when done.

Show as a compact vertical list of steps:
  Each step:
    - Status icon: spinner (running) | green check (done) | red X (error)
    - Title: "Reading latest 10-Q filing..."
    - Finding (when done): small gray italic text below title
      e.g. "Revenue grew 12% YoY, services segment expanding"
    - Duration: "1.2s" shown at right (when done)
  
  Steps appear one by one as SSE reasoning_step events arrive.
  Running step has a subtle pulse animation on the icon.
  All done steps collapse to a single summary line after 2 seconds:
    "✓ Analysis complete — 7 steps, 18.3s total"

After streaming is done, this panel hides automatically (or user can toggle it back with
"Show analysis steps" button). This keeps the focus on the report itself.

Use CSS transitions for smooth step appearance (slide down + fade in, 150ms each).
```

---

## PHASE 3 — Feature sections (Day 4–7)

### Prompt 3.1 — Peer comparison tab
```
Create src/pages/PeerComparison.tsx — the dedicated peer comparison view.

This is the second tab on a stock page: /stock/AAPL?tab=peers

Fetch from GET /api/peers/{ticker} using React Query:
  const { data, isLoading } = useQuery({
    queryKey: ['peers', ticker],
    queryFn: () => api.getPeers(ticker)
  })

LAYOUT:

Top section — "Comparing {ticker} to {N} sector peers in {Industry}"

COMPARISON TABLE (the main feature):
  Sticky header row with sortable columns
  Columns: Company | Mkt Cap | P/E | EV/EBITDA | Gross Margin | Rev Growth | Net Margin | Debt/Equity | Score
  
  Subject ticker row: highlighted with brand-50 background + brand-500 left border
  Peer rows: alternating white/gray-50
  
  Each numeric cell:
    - Color-coded relative to sector median:
      - Top quartile: text-green-600 + faint green background
      - Bottom quartile: text-red-600 + faint red background
      - Middle 50%: default text color
    - Hover tooltip: "{metric}: {value} vs sector median {median} ({percentile}th percentile)"
  
  Sortable: click column header to sort ascending/descending (client-side, no API call)
  
  Last column "Score": 0-100 composite attractiveness score from backend
    Show as a colored pill: ≥70 green, 40-70 amber, <40 red

AI NARRATIVE (below table):
  2-3 sentence AI-generated comparison from GET /api/peers/{ticker}/compare
  Show with citation badge for each claim
  Loading: skeleton text shimmer

MINI SNOWFLAKE COMPARISON (side panel or below):
  Show 3-4 mini snowflake pentagons side by side:
  Subject + top 3 peers
  Scale: 60px each, no labels — just the visual shape for quick comparison
  Clicking a mini snowflake highlights that company in the table

SUPERINVESTOR SECTION (at bottom):
  If superinvestor cluster exists for this ticker:
  "Smart Money Activity" card with:
  - Fund count and quarter
  - List of funds with their AUM%, entry change (new/increased)
  - "Signal strength" bar (0-10)
  If no cluster: small gray note "No superinvestor clustering detected this quarter"
```

### Prompt 3.2 — Filing diff redlines
```
Create src/components/FilingDiff.tsx — the filing diff redline viewer.

Props: diff: FilingDiff | null, loaded: boolean

This shows what changed between the current 10-Q and the prior quarter's 10-Q.
It's one of the most differentiating features — nobody else shows this to retail investors.

Design:

HEADER: "What changed: {ticker} 10-Q {current_period} vs {prior_period}"

TAB BAR: one tab per changed section (MD&A | Risk Factors | Financial Statements | Other)

For each section, show a diff viewer:
  - Additions in green (bg-green-50, text-green-900, left bar |) 
  - Deletions in red (bg-red-50, text-red-900, left bar |, strikethrough)
  - Unchanged context (normal text, slightly muted)
  
  Style similar to GitHub diff view but simpler:
    + Revenue increased 12% year over year driven by services growth.   ← addition
    - Revenue increased 8% year over year driven by hardware sales.     ← deletion

  Above diff: AI-generated 1-2 sentence summary of what changed in this section
  e.g. "Management significantly expanded risk disclosure around AI regulation — added 3 new
        risk factors not present in the prior quarter."

  If section has many changes: show first 10 additions/deletions, "+ Show N more" toggle

EMPTY STATE: If no significant changes: "No material changes detected in this section."

When loaded=false: skeleton with 3 gray diff-colored bars

ADD: "Why this matters" tooltip on the header (i icon):
  "Changes in SEC filings often signal important shifts before they appear in headlines.
   Red text = removed disclosures. Green text = new disclosures."
```

### Prompt 3.3 — Insider & congressional trades
```
Create src/components/InsiderActivity.tsx and src/components/CongressionalTrades.tsx

INSIDER ACTIVITY:
Props: cluster: InsiderCluster | null, loaded: boolean

If cluster detected:
  ALERT BANNER (amber/green depending on cluster_date recency):
  "🔔 Insider Cluster Detected — {cluster.insider_count} insiders bought ${cluster.total_value_usd}
   in the last 30 days"
  
  Signal strength meter: visual bar 0-10 with label ("Moderate signal", "Strong signal")
  
  Below: collapsible table of individual trades:
    | Name | Role | Shares | Value | Date | Type |
    | CEO  | CEO  | 50,000 | $2.3M | Mar 15 | Open Market Buy |
  
  Role badges: CEO (purple), CFO (blue), Director (gray)
  Source link: "[SEC Form 4 ↗]" linking to actual EDGAR filing

If no cluster: "No unusual insider buying activity in the last 30 days."

CONGRESSIONAL TRADES:
  Small card (less prominent than insider cluster):
  If trades exist for this ticker in last 90 days:
    Header: "Congressional Trading Activity"
    List: politician name, party badge (D/R), transaction type, amount range, date
    Party color: D=blue-100 text, R=red-100 text (subtle, just pill colors)
    Note at bottom: "Disclosed per STOCK Act. 45-day reporting delay applies."
  
  If none: "No recent congressional trades reported for this ticker."
```

### Prompt 3.4 — Social sentiment section
```
Create src/components/SentimentPulse.tsx

Props: sentiment: SentimentPulse | null, loaded: boolean

Design:
  HEADER: "Reddit Sentiment" with r/wallstreetbets and r/stocks icons

  GAUGE (semicircular):
    Show sentiment score (-1 to +1) as a gauge needle
    Left zone (-1 to -0.3): red "Bearish"
    Center (-0.3 to +0.3): gray "Neutral"  
    Right zone (+0.3 to +1): green "Bullish"
    Needle animates from center to actual score (400ms ease) when data loads
    
    Below gauge: "{mention_count} mentions in the past week"

  TOP POSTS (3 items, compact):
    Each post: subreddit badge | title (truncated to 60 chars) | score arrows | sentiment dot
    sentiment dot: green (>0.3), gray, red (<-0.3)
    Clicking a post opens the url in new tab

  DISCLAIMER (small, gray): "Sentiment from public Reddit posts. Not a trading signal."

  When loaded=false: gray semicircle + 3 shimmer rows
```

---

## PHASE 4 — Export & downloads (Day 6–8)

### Prompt 4.1 — Export menu
```
Create src/components/ExportMenu.tsx — the download/export options.

A dropdown button in the top nav (shown only on stock report pages):
  Button text: "Export ↓"  
  Dropdown items:
    [↓] Download PDF Report (1 page)
    [↓] Download Excel Workbook
    [↓] Download PowerPoint (5 slides)
    [📋] Copy Verdict Summary (copies plain text to clipboard)

Each item triggers an API call to the backend export endpoints:
  PDF: GET /api/stock/{ticker}/export/pdf  → downloads {ticker}_report.pdf
  Excel: GET /api/stock/{ticker}/export/excel → downloads {ticker}_research.xlsx
  PPTX: GET /api/stock/{ticker}/export/pptx → downloads {ticker}_deck.pptx

Download implementation (don't navigate away — use blob download):
  async function downloadFile(endpoint: string, filename: string) {
    const response = await fetch(`${API_URL}${endpoint}`)
    const blob = await response.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = filename; a.click()
    URL.revokeObjectURL(url)
  }

While downloading: show loading spinner inside the button, disable other options.
On success: brief toast notification "Downloaded {filename}"
On error: toast "Download failed — please try again"

"Copy Verdict Summary" action copies this text to clipboard:
  "{company_name} ({ticker}) — {VERDICT} ({confidence}% confidence)
   {plain_english_summary}
   
   Bull case: {bull1} | {bull2} | {bull3}
   Risk factors: {risk1} | {risk2} | {risk3}
   
   Source: [App Name] — Data from SEC EDGAR and DefeatBeta API"
```

### Prompt 4.2 — 1-page PDF preview
```
Create src/components/PDFPreview.tsx — client-side PDF preview before download.

Optional feature: show a preview of the 1-page report before downloading.
Clicking "Download PDF Report" first shows a modal with the PDF preview, then a "Download" button.

Use @react-pdf/renderer (npm install @react-pdf/renderer) for client-side PDF generation
as an alternative to server-side. This way the preview renders instantly.

Build ReportDocument component using react-pdf:

  A4 page (595px × 842px):
  
  TOP SECTION:
    - Company name + ticker (large, bold)
    - Generated date
    - Verdict badge (colored rectangle): BUY / WAIT / AVOID in large text
    - Confidence: "83% confidence"
    - 2-3 line summary
  
  MIDDLE SECTION (two columns):
    Left column "Bull Case":
      • Point 1 text (cited)
        [Source: AAPL 10-Q Q3 2024]
      • Point 2 text...
      • Point 3 text...
    
    Right column "Risk Factors":
      • Risk 1 text (cited)
      ...
  
  KEY METRICS TABLE (below columns):
    | Metric | Value | vs Sector |
    | P/E Ratio | 28.3x | Above avg |
    | Gross Margin | 45.2% | Top quartile |
    | Revenue TTM | $394B | — |
    | EV/EBITDA | 22.1x | Avg |
    | Debt/Equity | 1.73 | Below avg |
  
  FOOTER:
    "Data from SEC EDGAR and DefeatBeta API. Not financial advice. Generated by StockAI."

Show in a modal dialog when user clicks "Download PDF Report".
Modal has: [Preview] [Download] [Close] buttons.
If react-pdf fails to render: fall back to the server-side PDF download directly.
```

---

## PHASE 5 — Polish & integration (Day 8–10)

### Prompt 5.1 — Full stock report page assembly
```
Create src/pages/StockReport.tsx — the main page that assembles all components.

This page uses useStockStream(ticker) and renders sections as they arrive.

LAYOUT (reading order):

1. Tabs row: [Report] [Peer Comparison] [Filing Diff]  (Radix UI Tabs)
   URL reflects active tab: /stock/AAPL, /stock/AAPL?tab=peers, /stock/AAPL?tab=diff

2. Report tab content (top to bottom):
   a. ReasoningTrace (visible only while status === 'streaming')
   b. VerdictBanner (loaded when verdict section arrives)
   c. Two-column grid:
      Left (40%): SnowflakeChart (loaded when snowflake section arrives)
      Right (60%): Key metrics from FinancialSnapshot (loaded when financials arrives)
   d. Two-column grid:
      Left: CitedPoints type="bull" (loaded when verdict arrives)
      Right: CitedPoints type="risk" (loaded when verdict arrives)
   e. SentimentPulse (loaded when sentiment arrives)
   f. InsiderActivity + CongressionalTrades (side by side, loaded when those sections arrive)
   g. HedgingDetector results card (loaded when verdict arrives, from transcript analysis)

3. Peers tab: <PeerComparison ticker={ticker} />
4. Diff tab: <FilingDiff diff={state.filing_diff} loaded={state.filing_diff !== null} />

PAGE TITLE: Update document.title to "{ticker} — AI Stock Research" when ticker loads.

ERROR STATE: If status === 'error' for > 10s:
  Show centered message: "Having trouble loading {ticker}. This ticker may not be in our
  database yet — we're computing it now. Refresh in 60 seconds."

EMPTY STATE (ticker not found): If API returns 404:
  "We don't have data for '{ticker}' yet. It may not be in our covered universe."
```

### Prompt 5.2 — Performance & accessibility
```
Final polish pass on the frontend. Address these specific requirements:

PERFORMANCE:
1. Code splitting: lazy load PeerComparison and FilingDiff tabs (they're not shown by default)
   import { lazy, Suspense } from 'react'
   const PeerComparison = lazy(() => import('./PeerComparison'))

2. Memoize expensive components:
   - SnowflakeChart: React.memo (SVG doesn't need to re-render unless scores change)
   - PeerComparison table: useMemo for sorting calculations

3. Prefetch peer data when report tab loads (so switching to peers tab is instant):
   When streaming status === 'done', call queryClient.prefetchQuery(['peers', ticker])

4. Image: none. All visuals are SVG or CSS — no image downloads.

ACCESSIBILITY:
1. VerdictBanner: add aria-label="Investment verdict: BUY with 83% confidence"
2. SnowflakeChart SVG: add <title> and <desc> elements, role="img"
3. All icon buttons: add aria-label
4. FilingDiff: additions have aria-label="Addition:", deletions have "Deletion:"
5. Keyboard navigation: all interactive elements reachable via Tab key

MOBILE RESPONSIVE:
1. On mobile (<640px): single column layout (no side-by-side)
2. Snowflake chart: 200px on mobile, 280px on desktop
3. Peer comparison table: horizontal scroll on mobile (overflow-x: auto)
4. Nav search: full width on mobile
5. Export button: icon-only on mobile (no text)

DARK MODE (bonus — implement if time allows):
  Add Tailwind dark mode support: class="dark:bg-gray-900 dark:text-white"
  Toggle button in nav: sun/moon icon
  Store preference in localStorage
```

### Prompt 5.3 — Integration switch from mock to real backend
```
Final integration test. Switch frontend from mock server to real backend.

1. Change .env.local: VITE_API_URL=http://localhost:8000

2. Run full smoke test — visit these pages and verify:
   /                              → Landing page loads in <200ms
   /stock/AAPL                    → Stream starts within 1s, first content within 2s
   /stock/AAPL?tab=peers          → Peer table shows within 3s
   /stock/AAPL?tab=diff           → Filing diff shows for MD&A section
   Export PDF download            → PDF file downloads successfully
   Export Excel download          → .xlsx file downloads successfully

3. Verify SSE stream behavior:
   - Financials section fills in before verdict (correct order)
   - Reasoning trace shows 7 steps
   - Each step updates from "running" to "done"  
   - ReasoningTrace hides after "done" event

4. Verify citation links:
   - Click a citation badge → opens SEC.gov URL in new tab
   - All 6 citation badges (3 bull + 3 risk) have valid URLs

5. Check for console errors:
   - No CORS errors (backend must have Access-Control-Allow-Origin: http://localhost:3000)
   - No TypeScript type errors (run: npx tsc --noEmit)
   - No failed network requests in DevTools

6. Verify export panel works on a loaded report (not on skeleton state)

Share screen recording or screenshots with Person 1 and Person 2 showing the full flow.
```

---

## MERGE CHECKLIST (before combining with Person 1 & 2)

```
[ ] Landing page loads in <200ms (check Lighthouse)
[ ] SSE streaming: first shimmer visible within 50ms of navigating to /stock/AAPL
[ ] SkeletonReport renders before any API data arrives
[ ] Each section fills in independently as SSE events arrive (not all at once)
[ ] VerdictBanner shows correct color for buy/wait/avoid
[ ] SnowflakeChart pentagon animates on data load
[ ] CitedPoints: all 6 citation badges visible, at least one link is clickable
[ ] Peer comparison table sorts by clicking column headers
[ ] Superinvestor cluster card shows when data exists
[ ] FilingDiff shows additions in green, deletions in red
[ ] SentimentPulse gauge needle animates to correct position
[ ] InsiderCluster: cluster alert banner shows when cluster detected
[ ] Export PDF: clicking "Download PDF Report" triggers a file download
[ ] Export Excel: clicking "Download Excel" triggers a file download
[ ] Mobile: single column layout on screens < 640px
[ ] No TypeScript errors: npx tsc --noEmit passes clean
[ ] No console errors in Chrome DevTools

Tell Person 1 and Person 2: "Frontend ready on port 3000. Switch VITE_API_URL to 8000 to connect."
```
