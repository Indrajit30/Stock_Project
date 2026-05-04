const KEY = 'stockai.recentSearches'

export function getRecentSearches() {
  try {
    return JSON.parse(localStorage.getItem(KEY) || '[]') as string[]
  } catch {
    return []
  }
}

export function addRecentSearch(ticker: string) {
  const normalized = ticker.trim().toUpperCase()
  if (!normalized) return
  const next = [normalized, ...getRecentSearches().filter((item) => item !== normalized)].slice(0, 6)
  localStorage.setItem(KEY, JSON.stringify(next))
}
