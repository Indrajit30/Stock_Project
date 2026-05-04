export function formatCurrency(value: number | null | undefined) {
  if (value == null) return '-'
  const abs = Math.abs(value)
  if (abs >= 1_000_000_000_000) return `$${(value / 1_000_000_000_000).toFixed(1)}T`
  if (abs >= 1_000_000_000) return `$${(value / 1_000_000_000).toFixed(1)}B`
  if (abs >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`
  return `$${value.toLocaleString()}`
}

export function formatPercent(value: number | null | undefined) {
  if (value == null) return '-'
  return `${(value * 100).toFixed(1)}%`
}

export function formatRatio(value: number | null | undefined, suffix = 'x') {
  if (value == null) return '-'
  return `${value.toFixed(1)}${suffix}`
}

export function verdictLabel(verdict: string) {
  return verdict.toUpperCase()
}
