import numpy as np
import pandas as pd
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


model = SentenceTransformer('all-MiniLM-L6-v2')


movies_df['combined'] = (
    movies_df['title'].fillna('') + ' ' +
    movies_df['overview'].fillna('') + ' ' +
    movies_df['genres'].fillna('')
)

anime_df['combined'] = (
    anime_df['title'].fillna('') + ' ' +
    anime_df['description'].fillna('') + ' ' +
    anime_df['Genres'].fillna('')
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


alpha = 1.0
beta = 0.75
gamma = 0.25

def rocchio_update(query_vec, relevant_vecs, non_relevant_vecs):
    new_query = alpha * query_vec

    if relevant_vecs:
        new_query += beta * np.mean(relevant_vecs, axis=0)

    if non_relevant_vecs:
        new_query -= gamma * np.mean(non_relevant_vecs, axis=0)

    return new_query


def recommend(query, content_filter="all", top_n=50):
    query_cleaned = clean_text(query)
    query_tfidf = vectorizer.transform([query_cleaned])

    tfidf_scores = cosine_similarity(query_tfidf, tfidf_matrix).flatten()

    query_embedding = model.encode([query_cleaned])
    semantic_scores = cosine_similarity(query_embedding, all_embeddings).flatten()

    final_scores = 0.6 * tfidf_scores + 0.4 * semantic_scores

    liked_ids, disliked_ids = load_feedback()

    all_ids = (
        movies_df['id'].astype(str).tolist() +
        anime_df['myanimelist_id'].astype(str).tolist()
    )

    if liked_ids or disliked_ids:
        liked_indices = [i for i, id_ in enumerate(all_ids) if id_ in liked_ids]
        disliked_indices = [i for i, id_ in enumerate(all_ids) if id_ in disliked_ids]

        relevant_vecs = tfidf_matrix[liked_indices].toarray() if liked_indices else []
        non_relevant_vecs = tfidf_matrix[disliked_indices].toarray() if disliked_indices else []

        new_query = rocchio_update(query_tfidf.toarray()[0], relevant_vecs, non_relevant_vecs)
        tfidf_scores = cosine_similarity([new_query], tfidf_matrix).flatten()
        final_scores = 0.6 * tfidf_scores + 0.4 * semantic_scores

    n_movies = len(movies_df)

    if content_filter == "movies":
        final_scores[n_movies:] = 0
    elif content_filter == "anime":
        final_scores[:n_movies] = 0
    elif content_filter == "series":
        final_scores[:] = 0

    top_indices = final_scores.argsort()[::-1][:top_n]
    return top_indices, final_scores, all_ids


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
                "description": row['overview'],
                "genres": ", ".join([g['name'] for g in json.loads(row['genres'])]) if row['genres'] else "N/A",
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
                "description": row['description'],
                "genres": row['Genres'],
                "rating": row['Score'],
                "release_year": str(row['Released_Year']) if pd.notna(row['Released_Year']) else "N/A",
                "tfidf_score": round(score, 4),
                "poster_url": None,
                "watch_providers": None,
            }

        results.append(result)

    return results