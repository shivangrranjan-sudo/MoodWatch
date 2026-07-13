import { useCallback, useRef, useState } from 'react'
import Background from './components/Background.jsx'
import LandingPage from './components/LandingPage.jsx'
import ResultsPage from './components/ResultsPage.jsx'
import { searchFull } from './api.js'

export default function App() {
  const [view, setView] = useState('landing') // 'landing' | 'results'
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState('all')
  const [page, setPage] = useState(0)
  const [totalPages, setTotalPages] = useState(1)
  const [data, setData] = useState(null)
  const [status, setStatus] = useState('idle') // idle | loading | ready | error

  // Prefetched pages, keyed by page index, for instant pagination.
  const cacheRef = useRef({})

  const prefetch = useCallback(async (q, f, p, tp) => {
    if (p >= tp || cacheRef.current[p]) return
    try {
      cacheRef.current[p] = await searchFull(q, f, p)
    } catch {
      /* ignore prefetch failures */
    }
  }, [])

  const runSearch = useCallback(
    async (rawQuery, searchFilter, targetPage = 0) => {
      const q = (rawQuery || '').trim()
      if (!q) return

      setView('results')
      setQuery(q)
      setFilter(searchFilter)
      setPage(targetPage)

      if (targetPage === 0) cacheRef.current = {} // fresh search clears cache

      const cached = cacheRef.current[targetPage]
      if (cached) {
        setData(cached)
        setTotalPages(cached.total_pages || 1)
        setStatus('ready')
        prefetch(q, searchFilter, targetPage + 1, cached.total_pages || 1)
        return
      }

      setStatus('loading')
      try {
        const d = await searchFull(q, searchFilter, targetPage)
        cacheRef.current[targetPage] = d
        setData(d)
        setTotalPages(d.total_pages || 1)
        setStatus('ready')
        prefetch(q, searchFilter, targetPage + 1, d.total_pages || 1)
      } catch {
        setStatus('error')
      }
    },
    [prefetch],
  )

  const goHome = () => {
    setView('landing')
    setQuery('')
    setData(null)
    setPage(0)
    setStatus('idle')
    cacheRef.current = {}
  }

  return (
    <>
      <Background />
      {view === 'landing' ? (
        <LandingPage onSearch={runSearch} />
      ) : (
        <ResultsPage
          query={query}
          filter={filter}
          page={page}
          totalPages={totalPages}
          data={data}
          status={status}
          onSearch={runSearch}
          onHome={goHome}
          onChangePage={(dir) => runSearch(query, filter, page + dir)}
        />
      )}
    </>
  )
}
