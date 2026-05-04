import { Search } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { addRecentSearch, getRecentSearches } from '../lib/recentSearches'

interface SearchBoxProps {
  large?: boolean
  placeholder?: string
}

export default function SearchBox({ large = false, placeholder = 'Search ticker e.g. AAPL' }: SearchBoxProps) {
  const [value, setValue] = useState('')
  const [focused, setFocused] = useState(false)
  const [recent, setRecent] = useState<string[]>([])
  const inputRef = useRef<HTMLInputElement | null>(null)
  const navigate = useNavigate()

  useEffect(() => {
    setRecent(getRecentSearches())
  }, [focused])

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null
      if (event.key === '/' && target?.tagName !== 'INPUT' && target?.tagName !== 'TEXTAREA') {
        event.preventDefault()
        inputRef.current?.focus()
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [])

  const runSearch = (raw = value) => {
    const ticker = raw.trim().toUpperCase().replace(/[^A-Z.-]/g, '')
    if (!ticker) return
    addRecentSearch(ticker)
    setValue('')
    setFocused(false)
    navigate(`/stock/${ticker}`)
  }

  return (
    <div className="search-wrap" style={{ maxWidth: large ? 620 : undefined, margin: large ? '0 auto' : undefined }}>
      <form
        className="search-box"
        onSubmit={(event) => {
          event.preventDefault()
          runSearch()
        }}
      >
        <Search aria-hidden="true" size={18} className="muted" />
        <input
          ref={inputRef}
          value={value}
          onChange={(event) => setValue(event.target.value.toUpperCase())}
          onFocus={() => setFocused(true)}
          onBlur={() => window.setTimeout(() => setFocused(false), 120)}
          placeholder={placeholder}
          aria-label="Search stock ticker"
        />
      </form>
      {focused && recent.length > 0 ? (
        <div className="recent-menu">
          {recent.map((ticker) => (
            <button key={ticker} type="button" className="recent-item" onMouseDown={() => runSearch(ticker)}>
              <strong>{ticker}</strong>
              <span className="muted">Recent</span>
            </button>
          ))}
        </div>
      ) : null}
    </div>
  )
}
