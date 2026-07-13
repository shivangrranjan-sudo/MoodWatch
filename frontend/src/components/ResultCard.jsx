import { useState } from 'react'
import { sendFeedback, fetchTrailer } from '../api.js'

function capitalize(str) {
  return str ? str.charAt(0).toUpperCase() + str.slice(1) : ''
}

export default function ResultCard({ result, query, open, onToggle, position = 0 }) {
  const [trailerUrl, setTrailerUrl] = useState(null)
  const [trailerFetched, setTrailerFetched] = useState(false)
  const [feedback, setFeedback] = useState(null) // 'like' | 'dislike' | null

  const genres = (result.genres || '')
    .split(',')
    .slice(0, 2)
    .map((g) => g.trim())
    .filter(Boolean)
  const providers = (result.providers || []).slice(0, 4)
  const snippets = (result.snippets || []).slice(0, 2)
  const scorePct = result.match_pct || 0

  // Every card gets a working Trailer button. Anime (and movies without a cached
  // TMDB trailer) fall back to a YouTube search, whose top hit is the trailer.
  const ytQuery = `${result.title}${result.content_type === 'anime' ? ' anime' : ''} trailer`
  const ytSearch = `https://www.youtube.com/results?search_query=${encodeURIComponent(ytQuery)}`
  const trailerHref = trailerUrl || ytSearch

  const handleToggle = async () => {
    const willOpen = !open
    onToggle()
    // Lazy-load the trailer only when the card is expanded, movies only.
    if (willOpen && result.content_type === 'movie' && !trailerFetched) {
      setTrailerFetched(true)
      try {
        const data = await fetchTrailer(result.id)
        if (data.trailer_url) setTrailerUrl(data.trailer_url)
      } catch {
        /* ignore trailer failures */
      }
    }
  }

  const handleFeedback = (type) => {
    if (feedback === type) {
      setFeedback(null)
      return
    }
    setFeedback(type)
    sendFeedback(result.id, type, query).catch(() => {})
  }

  return (
    <div className="result-card" style={{ animationDelay: `${Math.min(position, 9) * 0.04}s` }}>
      <div className="card-compact" onClick={handleToggle}>
        <div className="card-poster">
          {result.poster_url ? (
            <img src={result.poster_url} alt={result.title} loading="lazy" />
          ) : (
            <i className={`ti ${result.content_type === 'movie' ? 'ti-movie' : 'ti-device-tv'}`}></i>
          )}
        </div>
        <div className="card-body">
          <div className="card-top">
            <span className="card-title">{result.title}</span>
            <span className="card-year">{result.release_year || ''}</span>
          </div>
          <div className="badges">
            <span className={`badge badge-${result.content_type}`}>
              {capitalize(result.content_type)}
            </span>
            {genres.map((g, i) => (
              <span key={i} className="badge badge-genre">{g}</span>
            ))}
          </div>
          <div className="meta-row">
            <span className="imdb-pill">
              <i className="ti ti-star" style={{ fontSize: 10 }}></i> {result.rating || 'N/A'}
            </span>
            <div className="score-wrap">
              <div className="score-bg">
                <div className="score-fill" style={{ width: `${Math.min(scorePct, 99)}%` }}></div>
              </div>
              <span className="score-label">{scorePct}% match</span>
            </div>
          </div>
          <div className="card-footer-row">
            <span className="expand-hint">
              <i className="ti ti-chevron-down" style={{ fontSize: 11 }}></i> Details
            </span>
            <a
              className="btn-trailer"
              href={trailerHref}
              target="_blank"
              rel="noreferrer"
              onClick={(e) => e.stopPropagation()}
            >
              <i className="ti ti-player-play"></i> Trailer
            </a>
          </div>
        </div>
      </div>

      <div className={`expanded-panel ${open ? 'open' : ''}`}>
        <div>
          <p className="exp-label">About</p>
          <p className="exp-desc">{result.description || 'No description available.'}</p>
        </div>
        <div>
          <p className="exp-label">What people say</p>
          {snippets.length ? (
            snippets.map((s, i) => (
              <div key={i} className="review-item">"{s.substring(0, 160)}..."</div>
            ))
          ) : (
            <span style={{ fontSize: 12, color: '#1e3d55' }}>No reviews available</span>
          )}
        </div>
        <div>
          <p className="exp-label">Available on</p>
          {providers.length ? (
            <div className="platforms">
              {providers.map((p, i) => (
                <span key={i} className="platform-pill">{p}</span>
              ))}
            </div>
          ) : (
            <span style={{ fontSize: 12, color: '#1e3d55' }}>Not available in your region</span>
          )}
        </div>
        <div className="exp-score-row">
          <span>Text match: {result.tfidf_score}</span>
          <span>·</span>
          <span>Sentiment: {result.polarity !== null ? result.polarity : 'N/A'}</span>
          <span>·</span>
          <span>Overall: {result.final_score}</span>
        </div>
        <div className="exp-actions">
          <button
            className={`btn-like ${feedback === 'like' ? 'active' : ''}`}
            onClick={() => handleFeedback('like')}
          >
            <i className="ti ti-heart"></i> Like
          </button>
          <button
            className={`btn-dislike ${feedback === 'dislike' ? 'active' : ''}`}
            onClick={() => handleFeedback('dislike')}
          >
            <i className="ti ti-thumb-down"></i> Not for me
          </button>
        </div>
      </div>
    </div>
  )
}
