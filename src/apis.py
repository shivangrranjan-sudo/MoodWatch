import os
import requests
from dotenv import load_dotenv

load_dotenv()

TMDB_API_KEY = os.getenv("TMDB_API_KEY")
TMDB_BASE_URL = "https://api.themoviedb.org/3"
JIKAN_BASE_URL = "https://api.jikan.moe/v4"

#TMDB -------

def get_movie_details(tmdb_id):
    url = f"{TMDB_BASE_URL}/movie/{tmdb_id}"
    params = {"api_key": TMDB_API_KEY, "language": "en-US"}
    r = requests.get(url, params=params)
    if r.status_code != 200:
        return None
    d = r .json()
    return {
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


def get_series_details(tmdb_id):
    url = f"{TMDB_BASE_URL}/tv/{tmdb_id}"
    params = {"api_key": TMDB_API_KEY, "language": "en-US"}
    r = requests.get(url, params= params)
    if r.status != 200:
        return None
    d = r.json()
    return {
        "id": f"tv_{tmdb_id}", #tv_id to avoid overlapping with movies
        "title": d.get("name"),
        "content_type": "series",
        "poster_url": f"https://image.tmdb.org/t/p/w500{d.get('poster_path')}" if d.get("poster_path") else None,
        "description": d.get("overview"),
        "genres": ", ".join([g["name"] for g in d.get("genres", [])]),
        "rating": d.get("vote_average"),
        "runtime": str(d.get("episode_run_time", [None])[0]) + " min/ep" if d.get("episode_run_time") else None,
        "release_year": d.get("first_air_date", "")[:4],
    }


def get_watch_providers(tmdb_id, content_type="movie"):
    endpoint = "movie" if content_type == "movie" else "tv"
    url = f"{TMDB_BASE_URL}/{endpoint}/{tmdb_id}/watch/providers"
    params = {"api_key": TMDB_API_KEY}
    r = requests.get(url, params=params)
    if r.status_code != 200:
        return None, None
    results = r.json().get("results", {})
    in_data = results.get("IN", {})  # IN = India
    flatrate = [p["provider_name"] for p in in_data.get("flatrate", [])]
    link = in_data.get("link")
    return flatrate, link


# JIKAN ---------

def get_anime_details(mal_id):
    url = f"{JIKAN_BASE_URL}/anime/{mal_id}"
    r = requests.get(url)
    if r.status_code != 200:
        return None
    d = r.json().get("data", {})
    return {
        "id": f"anime_{mal_id}",
        "title": d.get("title_english") or d.get("title"),
        "content_type": "anime",
        "poster_url": d.get("images", {}).get("jpg", {}).get("large_image_url"),
        "description": d.get("synopsis"),
        "genres": ", ".join([g["name"] for g in d.get("genres", [])]),
        "rating": d.get("score"),
        "runtime": str(d.get("duration")),
        "release_year": str(d.get("year")) if d.get("year") else None,
    }

