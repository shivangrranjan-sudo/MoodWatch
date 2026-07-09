from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from src.apis import get_anime_details, get_movie_details, get_movie_trailer, get_watch_providers
from src.db import init_db, save_feedback
from src.evaluation import compute_metrics
from src.recommender import get_results, recommend
from src.sentiment import get_sentiment
import math
import os
import time
from concurrent.futures import ThreadPoolExecutor


load_dotenv()
init_db()

app = FastAPI()

# Serve static files (CSS, images)
app.mount("/static", StaticFiles(directory="static"), name="static")

# ── React frontend (Vite build) ─────────────────────────────────────────────────
# If the React app has been built (`cd frontend && npm run build`), serve it.
# Otherwise fall back to the original vanilla template so the app still runs.
SPA_DIST = os.path.join(os.path.dirname(__file__), "frontend", "dist")
SPA_INDEX = os.path.join(SPA_DIST, "index.html")
SPA_ASSETS = os.path.join(SPA_DIST, "assets")
if os.path.isdir(SPA_ASSETS):
    app.mount("/assets", StaticFiles(directory=SPA_ASSETS), name="assets")


# ── Serve the frontend ─────────────────────────────────────────────────────────
@app.get("/")
def index():
    if os.path.exists(SPA_INDEX):
        return FileResponse(SPA_INDEX)
    return FileResponse("templates/index.html")


@app.get("/dashboard")
def dashboard():
    return FileResponse("templates/dashboard.html")


@app.get("/dashboard/metrics")
def dashboard_metrics(top_k: int = 10):
    safe_top_k = max(1, min(top_k, 50))
    return compute_metrics(top_k=safe_top_k)


# ── Search endpoint ────────────────────────────────────────────────────────────
class SearchRequest(BaseModel):
    query: str
    filter: str = "all"
    page: int = 0
    page_size: int = 10

@app.post("/search")
def search(body: SearchRequest):
    top_indices, final_scores, all_ids = recommend(body.query, content_filter=body.filter)
    results = get_results(top_indices, final_scores, all_ids)
    
    # Clean NaN values so JSON can serialize them
    def clean(val):
        if isinstance(val, float) and math.isnan(val):
            return None
        return val
    
    cleaned = [
        {k: clean(v) for k, v in result.items()}
        for result in results
    ]
    
    return {"results": cleaned}


# ── Feedback endpoint ──────────────────────────────────────────────────────────
class FeedbackRequest(BaseModel):
    title_id: str
    feedback_type: str
    query: str = ""

@app.post("/feedback")
def feedback(body: FeedbackRequest):
    save_feedback(body.title_id, body.feedback_type, body.query)
    return {"status": "ok"}


@app.get("/enrich/{content_type}/{id}")
def enrich(content_type: str, id: str):
    def clean(val):
        if isinstance(val, float) and math.isnan(val):
            return None
        return val

    result = {}

    if content_type == "movie":
        tmdb_data = get_movie_details(id)
        if tmdb_data:
            result['poster_url'] = tmdb_data.get('poster_url')
            result['release_year'] = tmdb_data.get('release_year')
        providers, _ = get_watch_providers(id, 'movie')
        result['providers'] = providers or []

    elif content_type == "anime":
        mal_id = id.replace('anime_', '')
        anime_data = get_anime_details(mal_id)
        if anime_data:
            result['poster_url'] = anime_data.get('poster_url')
        result['providers'] = []

    return result


@app.get("/sentiment/{content_type}/{id}")
def sentiment(content_type: str, id: str, title: str):
    def clean(val):
        if isinstance(val, float) and math.isnan(val):
            return None
        return val

    tmdb_id = int(id) if content_type == "movie" else None
    polarity, snippets = get_sentiment(
        id, title,
        tmdb_id=tmdb_id,
        content_type=content_type
    )

    return {
        "polarity": clean(polarity),
        "snippets": snippets or []
    }

@app.post("/search-full")
def search_full(body: SearchRequest):
    request_start = time.time()
    print(f"REQUEST STARTED")

    def clean(val):
        if isinstance(val, float) and math.isnan(val):
            return None
        return val

    # Step 1 — ML pipeline (fast, gets all 50)
    t0 = time.time()

    top_indices, final_scores, all_ids = recommend(body.query, content_filter=body.filter, top_n=50)
    results = get_results(top_indices, final_scores, all_ids)
    print(f"ML pipeline: {time.time() - t0:.2f}s")


    # Step 2 — paginate BEFORE enrichment
    start = body.page * body.page_size
    end = start + body.page_size
    page_results = results[start:end]
    total = len(results)
    total_pages = (total + body.page_size - 1) // body.page_size if body.page_size else 0

    # Best score in the whole result set — used to scale the "% match" so the top
    # hit reads ~99% and the rest fall off honestly, instead of everything pinning
    # at the old cosmetic 99% cap.
    top_score = max((r['tfidf_score'] for r in results), default=1.0) or 1.0

    # Step 3 — enrich only current page. Each movie needs up to two TMDB calls
    # (details + providers); doing them sequentially made cold-cache searches take
    # 20-30s, so enrich all page results in parallel — the calls are pure I/O.
    t1 = time.time()

    def enrich_one(result):
        result = {k: clean(v) for k, v in result.items()}

        if result['content_type'] == 'movie':
            tmdb_data = get_movie_details(result['id'])
            if tmdb_data:
                result['poster_url'] = tmdb_data.get('poster_url')
                result['release_year'] = tmdb_data.get('release_year')
            providers, _ = get_watch_providers(result['id'], 'movie')
            result['providers'] = providers or []

        elif result['content_type'] == 'anime':
            # Poster is already set from the catalog's MAL CDN url in get_results().
            # No Jikan call needed here (it was slow/rate-limited and the frontend
            # doesn't use anime trailers), so anime searches are faster too.
            result['providers'] = []

        if result.get('release_year'):
            result['release_year'] = str(result['release_year']).replace('.0', '')

        tmdb_id = int(result['id']) if result['content_type'] == 'movie' else None
        polarity, snippets = get_sentiment(
            result['id'], result['title'],
            tmdb_id=tmdb_id,
            content_type=result['content_type'],
            fetch_missing=False
        )
        result['polarity'] = clean(polarity)
        result['snippets'] = snippets or []

        result['final_score'] = (
            round(0.7 * result['tfidf_score'] + 0.3 * polarity, 4)
            if polarity is not None
            else result['tfidf_score']
        )
        result['match_pct'] = round(min(result['tfidf_score'] / top_score, 1.0) * 99, 1)
        return result

    with ThreadPoolExecutor(max_workers=10) as pool:
        enriched = list(pool.map(enrich_one, page_results))

    print(f"Enrichment total: {time.time() - t1:.2f}s")

    # Step 4 — sort current page by final score
    enriched = sorted(enriched, key=lambda x: x['final_score'], reverse=True)

    t2 = time.time()
    print(f"Time before building response: {t2 - t0:.2f}s")

    response_data = {
        "results": enriched,
        "page": body.page,
        "total_pages": total_pages,
        "total": total
    }
    if total == 0:
        response_data["message"] = "Couldn't find a good match. Try a clearer mood or genre."

    print(f"Time to build dict: {time.time() - t2:.4f}s",  flush=True)

    print(f"REQUEST ENDING, total internal time: {time.time() - request_start:.2f}s",  flush=True)

    return response_data

@app.get("/trailer/{tmdb_id}")
def get_trailer(tmdb_id: str):
    trailer_url = get_movie_trailer(tmdb_id)
    return {"trailer_url": trailer_url}

@app.get("/ping")
def ping():
    return {"status": "ok"}

