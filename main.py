from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from dotenv import load_dotenv


load_dotenv()

app = FastAPI()

# Serve static files (CSS, images)
app.mount("/static", StaticFiles(directory="static"), name="static")


# ── Serve the frontend ─────────────────────────────────────────────────────────
@app.get("/")
def index():
    return FileResponse("templates/index.html")


# ── Search endpoint ────────────────────────────────────────────────────────────
class SearchRequest(BaseModel):
    query: str
    filter: str = "all"

@app.post("/search")
def search(body: SearchRequest):
    from src.recommender import recommend, get_results
    import math
    
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

@app.post("/feedback")
def feedback(body: FeedbackRequest):
    from src.db import save_feedback
    save_feedback(body.title_id, body.feedback_type)
    return {"status": "ok"}


@app.get("/enrich/{content_type}/{id}")
def enrich(content_type: str, id: str):
    from src.apis import get_movie_details, get_anime_details, get_watch_providers
    import math

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
    from src.sentiment import get_sentiment
    import math

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
    from src.recommender import recommend, get_results
    from src.apis import get_movie_details, get_anime_details, get_watch_providers
    from src.sentiment import get_sentiment
    import math
    from src.apis import get_movie_details, get_anime_details, get_watch_providers, get_movie_trailer


    def clean(val):
        if isinstance(val, float) and math.isnan(val):
            return None
        return val

    # Step 1 — get base results
    top_indices, final_scores, all_ids = recommend(body.query, content_filter=body.filter)
    results = get_results(top_indices, final_scores, all_ids)

    # Step 2 — enrich each result
    enriched = []
    for result in results:
        # clean base fields
        result = {k: clean(v) for k, v in result.items()}

        # poster + providers
        if result['content_type'] == 'movie':
            tmdb_data = get_movie_details(result['id'])
            if tmdb_data:
                result['poster_url'] = tmdb_data.get('poster_url')
                result['release_year'] = tmdb_data.get('release_year')
            providers, _ = get_watch_providers(result['id'], 'movie')
            result['providers'] = providers or []

        elif result['content_type'] == 'anime':
            mal_id = result['id'].replace('anime_', '')
            anime_data = get_anime_details(mal_id)
            if anime_data:
                result['poster_url'] = anime_data.get('poster_url')
            result['providers'] = []
            result['trailer_url'] = None


        # fix release year formatting
        if result.get('release_year'):
            result['release_year'] = str(result['release_year']).replace('.0', '')

        # sentiment
        tmdb_id = int(result['id']) if result['content_type'] == 'movie' else None
        polarity, snippets = get_sentiment(
            result['id'], result['title'],
            tmdb_id=tmdb_id,
            content_type=result['content_type']
        )
        result['polarity'] = clean(polarity)
        result['snippets'] = snippets or []

        # final blended score
        result['final_score'] = (
            round(0.7 * result['tfidf_score'] + 0.3 * polarity, 4)
            if polarity is not None
            else result['tfidf_score']
        )

        result['match_pct'] = round(min(result['final_score'] * 150, 99), 1)

        enriched.append(result)

    # Step 3 — sort by final score
    enriched = sorted(enriched, key=lambda x: x['final_score'], reverse=True)

    return {"results": enriched}


@app.get("/trailer/{tmdb_id}")
def get_trailer(tmdb_id: str):
    from src.apis import get_movie_trailer
    trailer_url = get_movie_trailer(tmdb_id)
    return {"trailer_url": trailer_url}