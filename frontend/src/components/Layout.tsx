import { Download, GitBranch, Moon, Sun } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, Outlet, useLocation, useParams } from 'react-router-dom'
import ExportMenu from './ExportMenu'
import SearchBox from './SearchBox'

export default function Layout() {
  const location = useLocation()
  const params = useParams()
  const [dark, setDark] = useState(() => localStorage.getItem('stockai.theme') === 'dark')
  const onStockPage = location.pathname.startsWith('/stock/')
  const ticker = params.ticker?.toUpperCase()

  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark)
    localStorage.setItem('stockai.theme', dark ? 'dark' : 'light')
  }, [dark])

  return (
    <>
      <header className="top-nav">
        <div className="nav-inner">
          <Link to="/" className="brand-mark" aria-label="Stock Research AI home">
            <span className="brand-name">Stock Research AI</span>
            <span className="brand-tagline">Research in seconds</span>
          </Link>
          <SearchBox />
          <div className="nav-actions">
            {onStockPage && ticker ? <ExportMenu ticker={ticker} compactIcon={<Download size={16} />} /> : null}
            <button
              type="button"
              className="icon-button"
              aria-label="Toggle dark mode"
              onClick={() => setDark((current) => !current)}
            >
              {dark ? <Sun size={17} /> : <Moon size={17} />}
            </button>
            <a
              href="https://github.com/"
              target="_blank"
              rel="noreferrer"
              className="icon-button"
              aria-label="Open GitHub"
            >
              <GitBranch size={17} />
            </a>
          </div>
        </div>
      </header>
      <main className="main-content">
        <Outlet />
      </main>
    </>
  )
}
