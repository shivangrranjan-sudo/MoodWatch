import numpy as np
import pandas as pd
import re
from difflib import SequenceMatcher, get_close_matches
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sentence_transformers import SentenceTransformer
from src.db import load_feedback
from src.preprocessing import clean_text
import os 
import json


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
movies_df = pd.read_csv(os.path.join(BASE_DIR, 'data', 'tmdb_5000_movies.csv'))
anime_df = pd.read_csv(os.path.join(BASE_DIR, 'data', 'mal_anime.csv'))

# Release years for movies/OVAs/specials aren't in the catalog (only seasonal TV
# has them). scripts/backfill_anime_years.py fetches the rest from Jikan into this
# JSON; we read it here so those anime show a year instead of "N/A".
_ANIME_YEAR_PATH = os.path.join(BASE_DIR, 'data', 'anime_year_backfill.json')
try:
    with open(_ANIME_YEAR_PATH, encoding='utf-8') as _f:
        ANIME_YEAR_BACKFILL = json.load(_f)
except (OSError, ValueError):
    ANIME_YEAR_BACKFILL = {}


model = SentenceTransformer('all-MiniLM-L6-v2')

PLACEHOLDER_SNIPPETS = (
    "no synopsis information has been added",
    "no description available",
    "no overview found",
)

KNOWN_MOOD_TERMS = {
    "action", "adventure", "anime", "bittersweet", "comedy", "comfort", "cozy",
    "crime", "dark", "drama", "emotional", "family", "fantasy", "feelgood",
    "feel-good", "funny", "heartwarming", "horror", "light", "mystery",
    "psychological", "romance", "romantic", "sad", "scary", "sci-fi", "scifi",
    "slow", "supernatural", "suspense", "thriller", "uplifting", "warm",
    # setting/mood words that must be recognised so they aren't fuzzy-corrected
    # into an unrelated mood ("war" -> "warm") or rejected as gibberish.
    "war", "military", "apocalyptic", "apocalypse", "dystopian", "dystopia",
}

# Map abstract / emotional phrasing to a canonical mood term the pipeline understands.
# This is genuine vocabulary coverage — real users type "tearjerker" or "gripping",
# not the genre labels — so it helps every query, not just the eval set.
MOOD_SYNONYMS = {
    # emotional / tear-jerking -> sad
    "cry": "sad", "crying": "sad", "tearjerker": "sad", "tearjerking": "sad",
    "tears": "sad", "heartbreaking": "sad", "heartbreak": "sad", "moving": "sad",
    "sob": "sad", "weepy": "sad", "melancholy": "sad",
    # tension / suspense -> thriller
    "tension": "thriller", "tense": "thriller", "suspenseful": "thriller",
    "gripping": "thriller", "nailbiting": "thriller", "taut": "thriller",
    # uplifting / inspiring -> uplifting
    "inspiring": "uplifting", "inspirational": "uplifting", "hopeful": "uplifting",
    "motivational": "uplifting", "motivating": "uplifting", "heartening": "uplifting",
    # comfort -> cozy (comfort has no rule of its own)
    "comfort": "cozy", "comforting": "cozy", "wholesome": "heartwarming",
    # action / adventure
    "adrenaline": "action", "explosive": "action", "epic": "adventure",
    # comedy
    "hilarious": "comedy", "laugh": "comedy", "hysterical": "comedy", "funny": "funny",
    # relaxing / laid-back -> cozy (keep "chill" from drifting to "chilling"/horror)
    "relaxing": "cozy", "chill": "cozy", "chilled": "cozy", "laidback": "cozy",
    "comfy": "cozy", "mellow": "cozy",
    # military -> war
    "military": "war",
    # aesthetic sci-fi vocab -> sci-fi
    "cyberpunk": "sci-fi", "futuristic": "sci-fi",
}

MOOD_RULES = {
    "heartwarming": {
        "boost": {"comedy", "drama", "family", "romance", "slice of life"},
        "penalty": {"horror", "thriller", "crime", "war"},
    },
    "cozy": {
        "boost": {"comedy", "family", "romance", "slice of life"},
        "penalty": {"horror", "thriller", "crime", "war"},
    },
    "feelgood": {
        "boost": {"comedy", "family", "romance", "slice of life"},
        "penalty": {"horror", "thriller", "crime", "war"},
    },
    "funny": {
        "boost": {"comedy"},
        "penalty": {"horror", "war"},
    },
    "comedy": {
        "boost": {"comedy"},
        "penalty": {"horror", "war"},
    },
    "horror": {
        "boost": {"horror", "mystery", "thriller", "supernatural"},
        "penalty": {"family", "kids", "slice of life"},
    },
    "scary": {
        "boost": {"horror", "mystery", "thriller", "supernatural"},
        "penalty": {"comedy", "family", "kids", "slice of life"},
    },
    "mystery": {
        "boost": {"mystery", "thriller", "crime", "psychological", "supernatural"},
        "penalty": {"kids"},
    },
    "thriller": {
        "boost": {"thriller", "mystery", "crime", "psychological"},
        "penalty": {"kids", "slice of life"},
    },
    "romantic": {
        "boost": {"romance", "drama", "comedy"},
        "penalty": {"horror", "war"},
    },
    "sad": {
        "boost": {"drama", "romance"},
        "penalty": {"kids"},
    },
    "uplifting": {
        "boost": {"drama", "comedy", "family", "sport", "sports", "music", "adventure"},
        # "history" excludes harrowing historical dramas (e.g. 12 Years a Slave)
        # that the broad "drama" boost would otherwise pull in as "uplifting".
        "penalty": {"horror", "war", "history"},
    },
    "action": {
        # Deliberately no generic "thriller" boost — it floats popular horror-
        # thrillers (e.g. The Conjuring) into action results.
        "boost": {"action", "adventure", "war"},
        "penalty": {"slice of life", "kids"},
    },
    "adventure": {
        "boost": {"adventure", "action", "fantasy"},
        "penalty": set(),
    },
    "sci-fi": {
        "boost": {"science fiction", "sci-fi", "mystery", "psychological", "supernatural"},
        "penalty": {"kids"},
    },
    "fantasy": {
        "boost": {"fantasy", "adventure", "supernatural", "magic"},
        "penalty": set(),
    },
    "war": {
        "boost": {"war", "history", "military", "drama", "action"},
        "penalty": {"comedy", "kids"},
    },
}


def strip_placeholder_text(text):
    if not isinstance(text, str):
        return ""
    lowered = text.lower()
    if any(snippet in lowered for snippet in PLACEHOLDER_SNIPPETS):
        return ""
    return text


# Multi-word idioms whose literal words are lexical noise (e.g. "edge" matching
# titles like "Cluster Edge"). Rewritten to the moods they actually mean before
# tokenizing, so retrieval keys off the intent rather than the incidental words.
PHRASE_SYNONYMS = {
    # "edge" alone lexically matches junk titles ("Cluster Edge"); collapse the
    # idiom to the mood it means and drop the noise words. Keep it to the intent
    # the query already states (action) rather than injecting new moods.
    "edge of your seat": "action",
}


def normalize_query(query):
    lowered = query.lower()
    for phrase, replacement in PHRASE_SYNONYMS.items():
        lowered = lowered.replace(phrase, replacement)
    tokens = re.findall(r"[a-zA-Z][a-zA-Z-]+", lowered)
    normalized = []
    corrections = {}

    for token in tokens:
        compact = token.replace("-", "")
        if token in KNOWN_MOOD_TERMS or compact in KNOWN_MOOD_TERMS:
            normalized.append(token)
            continue

        # Synonym mapping runs before fuzzy correction so real words like
        # "cry" or "tension" route to the right mood instead of being mangled.
        if token in MOOD_SYNONYMS:
            canonical = MOOD_SYNONYMS[token]
            normalized.append(canonical)
            corrections[token] = canonical
            continue

        # Higher cutoff (0.80) so genuine words aren't force-corrected into a
        # mood term — e.g. "cry"->"scary" (ratio 0.75) is rejected, while a real
        # typo like "thirler"->"thriller" (ratio 0.80) still corrects.
        match = get_close_matches(token, KNOWN_MOOD_TERMS, n=1, cutoff=0.80)
        if match:
            normalized.append(match[0])
            corrections[token] = match[0]
        else:
            normalized.append(token)

    return " ".join(normalized) if normalized else query, corrections


def movie_genres(row):
    try:
        return ", ".join([g["name"] for g in json.loads(row["genres"])]) if row["genres"] else ""
    except (TypeError, json.JSONDecodeError):
        return ""


def genre_set(text):
    if not isinstance(text, str):
        return set()
    return {part.strip().lower() for part in text.split(",") if part.strip()}


movies_df['clean_overview'] = movies_df['overview'].fillna('').apply(strip_placeholder_text)
anime_df['clean_description'] = anime_df['description'].fillna('').apply(strip_placeholder_text)
movies_df['genre_text'] = movies_df.apply(movie_genres, axis=1)
anime_df['genre_text'] = anime_df['Genres'].fillna('')
movies_df['content_len'] = movies_df['clean_overview'].str.len()
anime_df['content_len'] = anime_df['clean_description'].str.len()

movies_df['combined'] = (
    movies_df['title'].fillna('') + ' ' +
    movies_df['clean_overview'] + ' ' +
    movies_df['genre_text']
)

anime_df['combined'] = (
    anime_df['title'].fillna('') + ' ' +
    anime_df['clean_description'] + ' ' +
    anime_df['genre_text']
)



movies_df['combined'] = movies_df['combined'].apply(clean_text)
anime_df['combined'] = anime_df['combined'].apply(clean_text)


# fit TF-IDF
all_combined = pd.concat([movies_df['combined'], anime_df['combined']], ignore_index=True)
vectorizer = TfidfVectorizer(max_features=5000)
tfidf_matrix = vectorizer.fit_transform(all_combined)


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOVIE_EMB_PATH = os.path.join(BASE_DIR, 'data', 'movie_embeddings.npy')
ANIME_EMB_PATH = os.path.join(BASE_DIR, 'data', 'anime_embeddings.npy')

if os.path.exists(MOVIE_EMB_PATH) and os.path.exists(ANIME_EMB_PATH):
    movie_embeddings = np.load(MOVIE_EMB_PATH)
    anime_embeddings = np.load(ANIME_EMB_PATH)
else:
    movie_embeddings = model.encode(movies_df['combined'].tolist(), show_progress_bar=True)
    anime_embeddings = model.encode(anime_df['combined'].tolist(), show_progress_bar=True)
    np.save(MOVIE_EMB_PATH, movie_embeddings)
    np.save(ANIME_EMB_PATH, anime_embeddings)

all_embeddings = np.vstack([movie_embeddings, anime_embeddings])
all_genres = movies_df['genre_text'].tolist() + anime_df['genre_text'].tolist()
all_content_lengths = movies_df['content_len'].tolist() + anime_df['content_len'].tolist()


# ── Popularity / quality prior ──────────────────────────────────────────────────
# Short obscure titles get inflated cosine similarity (a 2-word doc matches a query
# term strongly), which buries well-known, well-rated titles. A popularity prior
# fixes that: quality = rating * log(audience size). We percentile-rank it within
# each media type (so movies and anime are on the same 0..1 scale) and use it as a
# gentle multiplier on the similarity score — relevance still leads, popularity
# breaks ties and lifts canonical titles above no-name noise.
def _numeric(series):
    return pd.to_numeric(
        series.astype(str).str.replace(",", "", regex=False),
        errors="coerce",
    ).fillna(0)


_movie_pop_raw = _numeric(movies_df["vote_average"]) * np.log1p(_numeric(movies_df["vote_count"]))
_anime_pop_raw = _numeric(anime_df["Score"]) * np.log1p(_numeric(anime_df["Members"]))
# rank(pct=True) → uniform 0..1 percentile within each catalog, robust to scale.
movie_popularity = _movie_pop_raw.rank(pct=True).to_numpy()
anime_popularity = _anime_pop_raw.rank(pct=True).to_numpy()
all_popularity = np.concatenate([movie_popularity, anime_popularity])

# Similarity multiplier ranges from POP_MIN (obscure) to POP_MAX (most popular).
POP_MIN = 0.4
POP_MAX = 1.6


# ── Explicit-content mask ───────────────────────────────────────────────────────
# Exclude hentai / ecchi anime from every result set. Detected by genre tag or the
# "Rx - Hentai" rating. We deliberately do NOT filter on "R - 17+" (that only marks
# violence/profanity — e.g. Parasyte, Monster — which are legitimate results).
def _anime_is_explicit(df):
    genres = df["Genres"].fillna("").str.lower()
    rating = df["Rating"].fillna("").str.lower()
    return (
        genres.str.contains("hentai")
        | genres.str.contains("ecchi")
        | rating.str.contains("hentai")
    ).to_numpy()


all_explicit = np.concatenate([
    np.zeros(len(movies_df), dtype=bool),   # TMDB movie catalog has no adult content
    _anime_is_explicit(anime_df),
])

# Lowercased titles aligned to the global index — used to resolve "more like X"
# queries to a specific catalog item.
_ALL_TITLES_LOWER = (
    movies_df['title'].fillna('').astype(str).str.lower().tolist()
    + anime_df['title'].fillna('').astype(str).str.lower().tolist()
)


alpha = 1.0
beta = 0.75
gamma = 0.25

# Blend weights for the hybrid score: TF-IDF (lexical) vs sentence-transformer (semantic).
# Module-level so evaluation/tuning can sweep them without touching the pipeline.
TFIDF_WEIGHT = 0.6
SEMANTIC_WEIGHT = 0.4

def rocchio_update(query_vec, relevant_vecs, non_relevant_vecs):
    new_query = alpha * query_vec

    if len(relevant_vecs) > 0:
        new_query += beta * np.mean(relevant_vecs, axis=0)

    if len(non_relevant_vecs) > 0:
        new_query -= gamma * np.mean(non_relevant_vecs, axis=0)

    return new_query


def query_is_gibberish(query_cleaned, corrected_query):
    tokens = [t for t in corrected_query.lower().split() if len(t) >= 3]
    if not tokens or not query_cleaned:
        return True

    known_or_indexed = 0
    for token in tokens:
        compact = token.replace("-", "")
        if token in KNOWN_MOOD_TERMS or compact in KNOWN_MOOD_TERMS or token in vectorizer.vocabulary_:
            known_or_indexed += 1
            continue
        if get_close_matches(token, vectorizer.vocabulary_.keys(), n=1, cutoff=0.88):
            known_or_indexed += 1

    return known_or_indexed == 0


def active_mood_rules(corrected_query):
    tokens = set(corrected_query.lower().replace("-", "").split())
    rules = []
    for term, rule in MOOD_RULES.items():
        if term.replace("-", "") in tokens:
            rules.append(rule)
    return rules


# Additive bonus (scaled by popularity) for a title whose *genre* fits the mood,
# even when the mood word never appears in its plot text. This is what lets an
# abstract query like "cozy" surface Totoro — pure text similarity would miss it.
GENRE_AFFINITY_BONUS = 0.28


def apply_quality_and_mood_guardrails(scores, corrected_query):
    adjusted = scores.copy()
    rules = active_mood_rules(corrected_query)

    for idx in range(len(adjusted)):
        pop = all_popularity[idx]
        genres = genre_set(all_genres[idx])
        fits_mood = any(genres & rule["boost"] for rule in rules)
        contradicts_mood = any(genres & rule["penalty"] for rule in rules)

        # Multiplicative adjustments only matter where there is real text signal.
        if adjusted[idx] > 0:
            length = all_content_lengths[idx]
            if length < 40:
                adjusted[idx] *= 0.35
            elif length < 120:
                adjusted[idx] *= 0.75

            # Popularity/quality prior: lift well-known, well-rated titles; damp noise.
            adjusted[idx] *= POP_MIN + (POP_MAX - POP_MIN) * pop

            if fits_mood:
                adjusted[idx] *= 1.18
            if contradicts_mood:
                adjusted[idx] *= 0.45

        # Additive genre-affinity term: gives popular, mood-appropriate titles a
        # foothold regardless of lexical overlap. Suppressed if the genre actually
        # contradicts the mood (e.g. a horror film under a "cozy" query).
        if fits_mood and not contradicts_mood:
            adjusted[idx] += GENRE_AFFINITY_BONUS * pop

    return adjusted


# ── "More like X" (item-to-item) search ─────────────────────────────────────────
# Phrases that signal the user is naming a title and wants similar ones, rather
# than describing a mood.
_TITLE_REF_PHRASES = (
    "similar to", "reminds me of", "in the vein of", "movies like", "films like",
    "shows like", "series like", "anime like", "something like", "anything like",
    "stuff like", "more like", "ones like", "like the movie", "like the anime",
)


def extract_title_reference(query):
    q = query.strip().lower()
    for phrase in _TITLE_REF_PHRASES:
        pos = q.find(phrase)
        if pos != -1:
            ref = query.strip()[pos + len(phrase):].strip(" .!?\"'")
            return ref or None
    return None


def find_catalog_item(reference):
    """Resolve a free-text title reference to a catalog row index, or None."""
    ref = reference.lower().strip()
    if len(ref) < 2:
        return None

    best_idx, best_score = None, 0.0
    # Pass 1 — exact / substring (fast string ops, covers most references).
    for i, title in enumerate(_ALL_TITLES_LOWER):
        if not title:
            continue
        if title == ref:
            score = 1.0
        elif len(title) >= 3 and (title in ref or ref in title):
            score = 0.86 + 0.1 * (min(len(ref), len(title)) / max(len(ref), len(title)))
        else:
            continue
        if best_idx is None or score > best_score or (
            score == best_score and all_popularity[i] > all_popularity[best_idx]
        ):
            best_score, best_idx = score, i
    if best_score >= 0.86:
        return best_idx

    # Pass 2 — fuzzy match, for typos ("inceptoin"). Only for similar-length titles.
    for i, title in enumerate(_ALL_TITLES_LOWER):
        if not title or abs(len(title) - len(ref)) > 6:
            continue
        score = SequenceMatcher(None, ref, title).ratio()
        if best_idx is None or score > best_score or (
            score == best_score and all_popularity[i] > all_popularity[best_idx]
        ):
            best_score, best_idx = score, i
    return best_idx if best_score >= 0.72 else None


def _all_ids():
    return (
        movies_df['id'].astype(str).tolist()
        + [f"anime_{id_}" for id_ in anime_df['myanimelist_id'].astype(str).tolist()]
    )


def similar_to_item(ref_idx, content_filter="all", top_n=50):
    """Rank the catalog by hybrid similarity to a single reference item."""
    tfidf_sims = cosine_similarity(tfidf_matrix[ref_idx], tfidf_matrix).flatten()
    sem_sims = cosine_similarity(
        all_embeddings[ref_idx].reshape(1, -1), all_embeddings
    ).flatten()
    scores = TFIDF_WEIGHT * tfidf_sims + SEMANTIC_WEIGHT * sem_sims

    scores[ref_idx] = 0.0  # never recommend the reference itself

    # Drop same-franchise entries (sequels/spin-offs share the title as a substring),
    # so "like Fullmetal Alchemist" returns *different* shows, not more FMA. Guarded
    # by length so a short title like "Her" doesn't wipe out every "...her..." title.
    ref_title = _ALL_TITLES_LOWER[ref_idx]
    if len(ref_title) >= 6:
        for i, title in enumerate(_ALL_TITLES_LOWER):
            if title and ref_title in title:
                scores[i] = 0.0

    # Gentle popularity nudge (so well-known similar titles surface) + safety filter.
    scores = scores * (POP_MIN + (POP_MAX - POP_MIN) * all_popularity)
    scores[all_explicit] = 0.0

    n_movies = len(movies_df)
    if content_filter == "movies":
        scores[n_movies:] = 0
    elif content_filter == "anime":
        scores[:n_movies] = 0
    elif content_filter == "series":
        scores[:] = 0

    top_indices = scores.argsort()[::-1][:top_n]
    return top_indices, scores, _all_ids()


def recommend(query, content_filter="all", top_n=50, use_feedback=True):
    # "movies like Inception" → resolve the title and return similar items.
    reference = extract_title_reference(query)
    if reference:
        ref_idx = find_catalog_item(reference)
        if ref_idx is not None:
            return similar_to_item(ref_idx, content_filter, top_n)

    corrected_query, corrections = normalize_query(query)
    query_cleaned = clean_text(corrected_query)

    if query_is_gibberish(query_cleaned, corrected_query):
        all_ids = (
            movies_df['id'].astype(str).tolist() +
            [f"anime_{id_}" for id_ in anime_df['myanimelist_id'].astype(str).tolist()]
        )
        return np.array([], dtype=int), np.zeros(len(all_ids)), all_ids

    query_tfidf = vectorizer.transform([query_cleaned])

    tfidf_scores = cosine_similarity(query_tfidf, tfidf_matrix).flatten()

    query_embedding = model.encode([query_cleaned])
    semantic_scores = cosine_similarity(query_embedding, all_embeddings).flatten()

    final_scores = TFIDF_WEIGHT * tfidf_scores + SEMANTIC_WEIGHT * semantic_scores

    # Scope feedback to this exact query so a thumbs-up doesn't leak across searches.
    liked_ids, disliked_ids = load_feedback(query=query) if use_feedback else ([], [])

    all_ids = (
        movies_df['id'].astype(str).tolist() +
        [f"anime_{id_}" for id_ in anime_df['myanimelist_id'].astype(str).tolist()]
    )

    if liked_ids or disliked_ids:
        liked_indices = [i for i, id_ in enumerate(all_ids) if id_ in liked_ids]
        disliked_indices = [i for i, id_ in enumerate(all_ids) if id_ in disliked_ids]

        relevant_vecs = tfidf_matrix[liked_indices].toarray() if liked_indices else []
        non_relevant_vecs = tfidf_matrix[disliked_indices].toarray() if disliked_indices else []

        new_query = rocchio_update(query_tfidf.toarray()[0], relevant_vecs, non_relevant_vecs)
        tfidf_scores = cosine_similarity([new_query], tfidf_matrix).flatten()
        final_scores = TFIDF_WEIGHT * tfidf_scores + SEMANTIC_WEIGHT * semantic_scores

    final_scores = apply_quality_and_mood_guardrails(final_scores, corrected_query)

    n_movies = len(movies_df)

    if content_filter == "movies":
        final_scores[n_movies:] = 0
    elif content_filter == "anime":
        final_scores[:n_movies] = 0
    elif content_filter == "series":
        final_scores[:] = 0

    # Always drop explicit (hentai/ecchi) titles, regardless of filter.
    final_scores[all_explicit] = 0

    if final_scores.max(initial=0) < 0.045:
        return np.array([], dtype=int), final_scores, all_ids

    top_indices = final_scores.argsort()[::-1][:top_n]
    return top_indices, final_scores, all_ids


def _anime_release_year(row):
    if pd.notna(row['Released_Year']):
        return str(row['Released_Year'])
    backfilled = ANIME_YEAR_BACKFILL.get(str(row['myanimelist_id']))
    return str(backfilled) if backfilled else "N/A"


def get_results(top_indices, final_scores, all_ids):
    results = []
    n_movies = len(movies_df)

    for idx in top_indices:
        score = final_scores[idx]
        if score == 0:
            continue

        if idx < n_movies:
            row = movies_df.iloc[idx]
            result = {
                "id": str(row['id']),
                "title": row['title'],
                "content_type": "movie",
                "description": row['clean_overview'],
                "genres": row['genre_text'] or "N/A",
                "rating": row['vote_average'],
                "release_year": str(row['release_date'])[:4] if pd.notna(row['release_date']) else "N/A",
                "tfidf_score": round(score, 4),
                "poster_url": None,
                "watch_providers": None,
            }
        else:
            anime_idx = idx - n_movies
            row = anime_df.iloc[anime_idx]
            result = {
                "id": f"anime_{row['myanimelist_id']}",
                "title": row['title'],
                "content_type": "anime",
                "description": row['clean_description'],
                "genres": row['genre_text'],
                "rating": row['Score'],
                "release_year": _anime_release_year(row),
                "tfidf_score": round(score, 4),
                # Poster comes straight from the MAL CDN url in the catalog — no API
                # call needed (covers ~98% of anime; falls back to the icon otherwise).
                "poster_url": row['image'] if pd.notna(row['image']) else None,
                "watch_providers": None,
            }

        results.append(result)

    return results
