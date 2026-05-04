import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { lazy, Suspense } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import Landing from './pages/Landing'
import StockReport from './pages/StockReport'

const queryClient = new QueryClient()
const PeerComparison = lazy(() => import('./pages/PeerComparison'))

function AppRoutes() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Landing />} />
        <Route path="/stock/:ticker" element={<StockReport />} />
        <Route
          path="/peers/:ticker"
          element={
            <Suspense fallback={<div className="section-card">Loading peers...</div>}>
              <PeerComparison />
            </Suspense>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <div className="app-shell">
          <AppRoutes />
        </div>
      </BrowserRouter>
    </QueryClientProvider>
  )
}

export default App
