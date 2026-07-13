// Thin wrappers around the FastAPI backend endpoints.

export async function searchFull(query, filter, page = 0, pageSize = 10) {
  const res = await fetch('/search-full', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, filter, page, page_size: pageSize }),
  })
  return res.json()
}

export async function sendFeedback(titleId, feedbackType, query) {
  return fetch('/feedback', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title_id: titleId, feedback_type: feedbackType, query }),
  })
}

export async function fetchTrailer(tmdbId) {
  const res = await fetch(`/trailer/${tmdbId}`)
  return res.json()
}
