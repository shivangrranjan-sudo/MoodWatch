import requests
import json
from datetime import datetime, timedelta
import sqlite3
import os
from dotenv import load_dotenv

load_dotenv()

OMDB_API_KEY = os.getenv("OMDB_API_KEY")
TMDB_API_KEY = os.getenv("TMDB_API_KEY")
OMDB_BASE_URL = "http://www.omdbapi.com/"
TMDB_BASE_URL = "https://api.themoviedb.org/3"


def fetch_tmdb_reviews(tmdb_id, content_type="movie"):
    try:
        endpoint = "movie" if content_type == "movie" else "tv"
        url = f"{TMDB_BASE_URL}/{endpoint}/{tmdb_id}/reviews"
        params = {"api_key": TMDB_API_KEY, "language": "en-US"}
        r = requests.get(url, params=params, timeout=5)
        if r.status_code != 200:
            return []
        results = r.json().get("results", [])
        snippets = []
        for review in results[:3]:
            content = review.get("content", "")
            if content:
                snippets.append(content[:200])
        return snippets
    except Exception:
        return []


def fetch_omdb_rating(title, tmdb_id=None, content_type="movie"):
    try:
        params = {
            "apikey": OMDB_API_KEY,
            "t": title,
            "type": "movie"
        }
        r = requests.get(OMDB_BASE_URL, params=params, timeout=5)
        if r.status_code != 200:
            return None, []

        data = r.json()
        if data.get("Response") == "False":
            params["type"] = "series"
            r = requests.get(OMDB_BASE_URL, params=params, timeout=5)
            data = r.json()

        if data.get("Response") == "False":
            return None, []

        imdb_rating = data.get("imdbRating")
        if not imdb_rating or imdb_rating == "N/A":
            return None, []

        normalized = float(imdb_rating) / 10

        if tmdb_id:
            snippets = fetch_tmdb_reviews(tmdb_id, content_type)
        else:
            snippets = []

        return normalized, snippets
    except Exception:
        return None, []
    
    

def get_sentiment(title_id, title, tmdb_id=None, content_type="movie"):
    conn = sqlite3.connect('moodwatch.db')
    cursor = conn.cursor()

    cursor.execute('SELECT polarity, review_snippets, cached_date FROM sentiment_cache WHERE title_id = ?', (title_id,))
    row = cursor.fetchone()

    if row:
        cached_date = datetime.strptime(row[2], "%Y-%m-%d %H:%M:%S")
        if datetime.now() - cached_date < timedelta(days=30):
            conn.close()
            return row[0], json.loads(row[1])

    polarity, snippets = fetch_omdb_rating(title, tmdb_id, content_type)

    if polarity is None:
        conn.close()
        return None, []

    cursor.execute('''
        INSERT OR REPLACE INTO sentiment_cache (title_id, polarity, review_snippets, cached_date)
        VALUES (?, ?, ?, ?)
    ''', (title_id, polarity, json.dumps(snippets), datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

    conn.commit()
    conn.close()
    return polarity, snippets