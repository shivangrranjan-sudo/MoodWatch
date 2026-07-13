import { useState } from 'react'

const FILTERS = [
  ['all', 'All'],
  ['movies', 'Movies'],
  // ['series', 'Series'],  // hidden until a series dataset exists (backend still supports it)
  ['anime', 'Anime'],
]

// Clickable starter queries so a first-time visitor (or an examiner) can try the
// app instantly without thinking up a mood.
const EXAMPLE_MOODS = [
  'dark horror',
  'feel-good comedy',
  'something to cry to',
  'movies like Inception',
  'epic space adventure',
]

export default function LandingPage({ onSearch }) {
  const [input, setInput] = useState('')
  const [filter, setFilter] = useState('all')

  const submit = () => onSearch(input, filter, 0)

  return (
    <div id="landing-page">
      <div className="mw-title">MoodWatch</div>
      <div className="mw-catchphrase">Your mood. Your next watch.</div>

      <div className="search-wrap">
        <div className="search-bar">
          <input
            className="search-input"
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && submit()}
            placeholder="I'm feeling something dark and emotional..."
            autoComplete="off"
            autoFocus
          />
          <button className="search-btn" onClick={submit}>Find my watch</button>
        </div>
        <div className="mood-filters">
          {FILTERS.map(([value, label]) => (
            <button
              key={value}
              className={`filter-btn ${filter === value ? 'active' : ''}`}
              onClick={() => setFilter(value)}
            >
              {label}
            </button>
          ))}
        </div>
        <div className="example-moods">
          <span className="example-label">Try</span>
          {EXAMPLE_MOODS.map((mood) => (
            <button
              key={mood}
              className="example-chip"
              onClick={() => { setInput(mood); onSearch(mood, filter, 0) }}
            >
              {mood}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
