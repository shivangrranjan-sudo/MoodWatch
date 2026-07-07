import os
import requests
from dotenv import load_dotenv
import json
from datetime import datetime, timedelta
from src.db import get_connection

load_dotenv()

TMDB_API_KEY = os.getenv("TMDB_API_KEY")
TMDB_BASE_URL = "https://api.themoviedb.org/3"
JIKAN_BASE_URL = "https://api.jikan.moe/v4"

#TMDB -------

def _safe_get(url, **kwargs):
    try:
        return requests.get(url, timeout=5, **kwargs)
    except requests.RequestException as exc:
        print(f"API request failed: {url} ({exc})")
        return None

def get_movie_details(tmdb_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT title, poster_url, description, genres, rating, runtime, release_year, cached_date FROM metadata_cache WHERE id = ?', (str(tmdb_id),))
    row = cursor.fetchone()

    if row:
        cached_date = datetime.strptime(row[7], "%Y-%m-%d %H:%M:%S")
        if datetime.now() - cached_date < timedelta(days=30):
            print(f"CACHE HIT: {tmdb_id}")
            conn.close()
            return {
                "id": str(tmdb_id),
                "title": row[0],
                "poster_url": row[1],
                "description": row[2],
                "genres": row[3],
                "rating": row[4],
                "runtime": row[5],
                "release_year": row[6],
                "content_type": "movie"
            }

    print(f"CACHE MISS: {tmdb_id}")
    url = f"{TMDB_BASE_URL}/movie/{tmdb_id}"
    params = {"api_key": TMDB_API_KEY, "language": "en-US"}
    r = _safe_get(url, params=params)
    if not r or r.status_code != 200:
        conn.close()
        return None
    d = r.json()

    result = {
        "id": str(tmdb_id),
        "title": d.get("title"),
        "content_type": "movie",
        "poster_url": f"https://image.tmdb.org/t/p/w500{d.get('poster_path')}" if d.get("poster_path") else None,
        "description": d.get("overview"),
        "genres": ", ".join([g["name"] for g in d.get("genres", [])]),
        "rating": d.get("vote_average"),
        "runtime": str(d.get("runtime")) + " min" if d.get("runtime") else None,
        "release_year": d.get("release_date", "")[:4],
    }

    cursor.execute('''
        INSERT OR REPLACE INTO metadata_cache 
        (id, title, content_type, poster_url, description, genres, rating, runtime, watch_providers, release_year, cached_date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        str(tmdb_id), result['title'], 'movie', result['poster_url'],
        result['description'], result['genres'], result['rating'],
        result['runtime'], None,  
        result['release_year'],
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))

    conn.commit()
    conn.close()
    return result


def get_series_details(tmdb_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT title, poster_url, description, genres, rating, runtime, release_year, cached_date FROM metadata_cache WHERE id = ?', (f"tv_{tmdb_id}",))
    row = cursor.fetchone()

    if row:
        cached_date = datetime.strptime(row[7], "%Y-%m-%d %H:%M:%S")
        if datetime.now() - cached_date < timedelta(days=30):
            conn.close()
            return {
                "id": f"tv_{tmdb_id}",
                "title": row[0],
                "poster_url": row[1],
                "description": row[2],
                "genres": row[3],
                "rating": row[4],
                "runtime": row[5],
                "release_year": row[6],
                "content_type": "series"
            }

    url = f"{TMDB_BASE_URL}/tv/{tmdb_id}"
    params = {"api_key": TMDB_API_KEY, "language": "en-US"}
    r = _safe_get(url, params=params)
    if not r or r.status_code != 200:
        conn.close()
        return None
    d = r.json()

    result = {
        "id": f"tv_{tmdb_id}",
        "title": d.get("name"),
        "content_type": "series",
        "poster_url": f"https://image.tmdb.org/t/p/w500{d.get('poster_path')}" if d.get("poster_path") else None,
        "description": d.get("overview"),
        "genres": ", ".join([g["name"] for g in d.get("genres", [])]),
        "rating": d.get("vote_average"),
        "runtime": str(d.get("episode_run_time", [None])[0]) + " min/ep" if d.get("episode_run_time") else None,
        "release_year": d.get("first_air_date", "")[:4],
    }

    cursor.execute('''
        INSERT OR REPLACE INTO metadata_cache
        (id, title, content_type, poster_url, description, genres, rating, runtime, release_year, cached_date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        f"tv_{tmdb_id}", result['title'], 'series', result['poster_url'],
        result['description'], result['genres'], result['rating'],
        result['runtime'], result['release_year'],
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))

    conn.commit()
    conn.close()
    return result


def get_watch_providers(tmdb_id, content_type="movie"):
    conn = get_connection()
    cursor = conn.cursor()
    
    cache_id = f"{content_type}_{tmdb_id}"
    cursor.execute('SELECT watch_providers, cached_date FROM metadata_cache WHERE id = ?', (str(tmdb_id),))
    row = cursor.fetchone()
    
    if row and row[0]:
        cached_date = datetime.strptime(row[1], "%Y-%m-%d %H:%M:%S")
        if datetime.now() - cached_date < timedelta(days=30):
            print(f"CACHE HIT (Watch provider): {tmdb_id}")
            conn.close()
            providers = json.loads(row[0])
            return providers, None
    
    endpoint = "movie" if content_type == "movie" else "tv"
    print(f"CACHE MISS (providers): {tmdb_id}")
    url = f"{TMDB_BASE_URL}/{endpoint}/{tmdb_id}/watch/providers"
    params = {"api_key": TMDB_API_KEY}
    r = _safe_get(url, params=params)
    if not r or r.status_code != 200:
        conn.close()
        return [], None
    results = r.json().get("results", {})
    in_data = results.get("US", {})
    flatrate = [p["provider_name"] for p in in_data.get("flatrate", [])]
    link = in_data.get("link")
    
    cursor.execute('''
        UPDATE metadata_cache SET watch_providers = ? WHERE id = ?
    ''', (json.dumps(flatrate), str(tmdb_id)))
    
    conn.commit()
    conn.close()
    return flatrate, link


# JIKAN ---------

def get_anime_details(mal_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT title, poster_url, description, genres, rating, runtime, release_year, trailer_url, cached_date FROM metadata_cache WHERE id = ?', (f"anime_{mal_id}",))
    row = cursor.fetchone()

    if row:
        cached_date = datetime.strptime(row[8], "%Y-%m-%d %H:%M:%S")
        if datetime.now() - cached_date < timedelta(days=30):
            conn.close()
            return {
                "id": f"anime_{mal_id}",
                "title": row[0],
                "poster_url": row[1],
                "description": row[2],
                "genres": row[3],
                "rating": row[4],
                "runtime": row[5],
                "release_year": row[6],
                "trailer_url": row[7],
                "content_type": "anime"
            }

    url = f"{JIKAN_BASE_URL}/anime/{mal_id}"
    r = _safe_get(url)
    if not r or r.status_code != 200:
        conn.close()
        return None
    d = r.json().get("data", {})

    result = {
        "id": f"anime_{mal_id}",
        "title": d.get("title_english") or d.get("title"),
        "content_type": "anime",
        "poster_url": d.get("images", {}).get("jpg", {}).get("large_image_url"),
        "description": d.get("synopsis"),
        "genres": ", ".join([g["name"] for g in d.get("genres", [])]),
        "rating": d.get("score"),
        "runtime": str(d.get("duration")),
        "release_year": str(d.get("year")) if d.get("year") else None,
        "trailer_url": d.get("trailer", {}).get("url"),
    }

    cursor.execute('''
        INSERT OR REPLACE INTO metadata_cache
        (id, title, content_type, poster_url, description, genres, rating, runtime, release_year, trailer_url, cached_date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        f"anime_{mal_id}", result['title'], 'anime', result['poster_url'],
        result['description'], result['genres'], result['rating'],
        result['runtime'], result['release_year'], result['trailer_url'],
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))

    conn.commit()
    conn.close()
    return result



#TRAILER ------ 

def get_movie_trailer(tmdb_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT trailer_url FROM metadata_cache WHERE id = ?', (str(tmdb_id),))
    row = cursor.fetchone()

    if row and row[0]:
        conn.close()
        return row[0]

    url = f"{TMDB_BASE_URL}/movie/{tmdb_id}/videos"
    params = {"api_key": TMDB_API_KEY, "language": "en-US"}
    r = _safe_get(url, params=params)
    if not r or r.status_code != 200:
        conn.close()
        return None
    videos = r.json().get("results", [])
    trailer_url = None
    for v in videos:
        if v.get("type") == "Trailer" and v.get("site") == "YouTube":
            trailer_url = f"https://www.youtube.com/watch?v={v['key']}"
            break

    if trailer_url:
        cursor.execute('UPDATE metadata_cache SET trailer_url = ? WHERE id = ?', (trailer_url, str(tmdb_id)))
        conn.commit()

    conn.close()
    return trailer_url
