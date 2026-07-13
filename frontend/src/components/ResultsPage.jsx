import { useEffect, useState } from 'react'
import ResultCard from './ResultCard.jsx'

const FILTERS = [
  ['all', 'All'],
  ['movies', 'Movies'],
  // ['series', 'Series'],  // hidden until a series dataset exists (backend still supports it)
  ['anime', 'Anime'],
]

export default function ResultsPage({
  query,
  filter,
  page,
  totalPages,
  data,
  status,
  onSearch,
  onHome,
  onChangePage,
}) {
  const [input, setInput] = useState(query)
  const [tbFilter, setTbFilter] = useState(filter)
  const [openIdx, setOpenIdx] = useState(null)

  // Keep the topbar input in sync when the active query changes.
  useEffect(() => { setInput(query) }, [query])
  // Reset which card is expanded, and scroll up, whenever the page/query changes.
  useEffect(() => {
    setOpenIdx(null)
    window.scrollTo(0, 0)
  }, [page, query, status])

  const results = data?.results || []
  const submit = () => onSearch(input, tbFilter, 0)

  return (
    <div id="results-page">
      <div className="results-topbar">
        <div className="topbar-title" onClick={onHome}>MoodWatch</div>
        <div className="topbar-search">
          <input
            className="topbar-input"
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && submit()}
            placeholder="Search again..."
            autoComplete="off"
          />
          <button className="topbar-search-btn" onClick={submit}>Search</button>
        </div>
        <div className="topbar-filters">
          {FILTERS.map(([value, label]) => (
            <button
              key={value}
              className={`topbar-filter-btn ${tbFilter === value ? 'active' : ''}`}
              // Selecting a filter immediately re-runs the active query with it,
              // so the results actually switch to that type instead of waiting
              // for another "Search" click.
              onClick={() => {
                setTbFilter(value)
                onSearch(query, value, 0)
              }}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="results-content">
        {status === 'loading' && (
          <div className="loading-state">
            <div className="spinner"></div>
            <span>Finding your next watch...</span>
          </div>
        )}

        {status === 'error' && (
          <div className="empty-state">
            <i className="ti ti-alert-circle" style={{ fontSize: 32, color: '#f09595' }}></i>
            <span>Something went wrong. Is the server running?</span>
          </div>
        )}

        {status === 'ready' && results.length === 0 && (
          <div className="empty-state">
            <i className="ti ti-mood-sad" style={{ fontSize: 32 }}></i>
            <span>{data?.message || 'No results found. Try a different mood.'}</span>
          </div>
        )}

        {status === 'ready' && results.length > 0 && (
          <>
            <p className="results-label">Results for "{query}" — {data.total} found</p>
            {results.map((result, i) => {
              const idx = page * 10 + i
              return (
                <ResultCard
                  key={`${result.id}-${idx}`}
                  result={result}
                  query={query}
                  position={i}
                  open={openIdx === idx}
                  onToggle={() => setOpenIdx(openIdx === idx ? null : idx)}
                />
              )
            })}
            {totalPages > 1 && (
              <div className="pagination">
                <button
                  className="page-btn"
                  disabled={page === 0}
                  onClick={() => onChangePage(-1)}
                >
                  ← Previous
                </button>
                <span className="page-info">Page {page + 1} of {totalPages}</span>
                <button
                  className="page-btn"
                  disabled={page >= totalPages - 1}
                  onClick={() => onChangePage(1)}
                >
                  Next →
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
