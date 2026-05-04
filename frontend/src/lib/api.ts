import type { PeerComparisonResponse, StockReport } from '../types/stock'

export const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

async function fetchJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_URL}${path}`)
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`)
  }
  return response.json() as Promise<T>
}

export async function downloadFile(endpoint: string, filename: string) {
  const response = await fetch(`${API_URL}${endpoint}`)
  if (!response.ok) {
    throw new Error(`Download failed: ${response.status}`)
  }
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
}

export const api = {
  getReport: (ticker: string) => fetchJson<StockReport>(`/api/stock/${ticker}/report`),
  getPeers: (ticker: string) => fetchJson<PeerComparisonResponse>(`/api/peers/${ticker}`),
  getPeerNarrative: (ticker: string) =>
    fetchJson<PeerComparisonResponse>(`/api/peers/${ticker}/compare`),
}
