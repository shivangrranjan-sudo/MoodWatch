import streamlit as st
from src.recommender import recommend, get_results
from src.apis import get_movie_details, get_series_details, get_watch_providers
from src.sentiment import get_sentiment
from src.db import save_feedback, init_db

init_db()

st.set_page_config(page_title="MoodWatch", layout="wide")
st.title("🎬 MoodWatch")
st.caption("Tell us your mood, we'll find your next watch.")

query = st.text_input("What's your mood right now?", placeholder="e.g. something dark and emotional, or a fun adventure")

col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    filter_all = st.button("🎬 All")
with col2:
    filter_movies = st.button("🎥 Movies")
with col3:
    filter_series = st.button("📺 Series")
with col4:
    filter_anime = st.button("⛩️ Anime")
with col5:
    pass

if "content_filter" not in st.session_state:
    st.session_state.content_filter = "all"

if filter_all:
    st.session_state.content_filter = "all"
if filter_movies:
    st.session_state.content_filter = "movies"
if filter_series:
    st.session_state.content_filter = "series"
if filter_anime:
    st.session_state.content_filter = "anime"

if query:
    st.write("---")

    with st.spinner("Finding your next watch..."):
        top_indices, final_scores, all_ids = recommend(
            query,
            content_filter=st.session_state.content_filter
        )
        results = get_results(top_indices, final_scores, all_ids)

    if not results:
        st.warning("No results found. Try a different mood or filter.")
        st.stop()

    if "page" not in st.session_state:
        st.session_state.page = 0

    page_size = 20
    start = st.session_state.page * page_size
    end = start + page_size
    current_results = results[start:end]

    for i, result in enumerate(current_results):
        if result['content_type'] == 'movie':
            tmdb_data = get_movie_details(result['id'])
            if tmdb_data:
                result['poster_url'] = tmdb_data.get('poster_url')
                result['release_year'] = tmdb_data.get('release_year', result['release_year'])

        tmdb_id = int(result['id']) if result['content_type'] == 'movie' else None
        polarity, snippets = get_sentiment(
            result['id'],
            result['title'],
            tmdb_id=tmdb_id,
            content_type=result['content_type']
        )

        if polarity is not None:
            final_score = 0.7 * result['tfidf_score'] + 0.3 * polarity
        else:
            final_score = result['tfidf_score']

        if result['content_type'] == 'movie':
            providers, watch_link = get_watch_providers(result['id'], 'movie')
        else:
            providers, watch_link = [], None

        with st.expander(f"**{result['title']}** — {round(final_score * 100, 1)}% Match", expanded=False):
            col1, col2 = st.columns([1, 3])

            with col1:
                if result['poster_url']:
                    st.image(result['poster_url'], use_container_width=True)
                else:
                    st.image("https://via.placeholder.com/150x220?text=No+Poster", use_container_width=True)

            with col2:
                st.markdown(f"**Type:** {result['content_type'].capitalize()} · **Year:** {result['release_year']} · **Rating:** {result['rating']}")
                st.write(result['description'])
                st.markdown(f"**Genres:** {result['genres']}")

                if providers:
                    st.markdown("**Streaming on:** " + " | ".join(providers))
                if watch_link:
                    st.markdown(f"[▶ Watch Now]({watch_link})")

                st.info(f"📊 TF-IDF: `{result['tfidf_score']:.4f}` | Sentiment: `{round(polarity, 4) if polarity else 'N/A'}` | Final: `{final_score:.4f}`")

                if snippets:
                    st.markdown("**What People Say:**")
                    for snippet in snippets:
                        st.caption(f"💬 {snippet}")

                btn_col1, btn_col2 = st.columns([1, 10])
                with btn_col1:
                    if st.button("👍", key=f"like_{i}"):
                        save_feedback(result['id'], 'like')
                        st.success("Noted!")
                with btn_col2:
                    if st.button("👎", key=f"dislike_{i}"):
                        save_feedback(result['id'], 'dislike')
                        st.success("Noted!")

    st.write("---")
    col1, col2, col3 = st.columns([1, 2, 1])

    with col1:
        if st.session_state.page > 0:
            if st.button("⬅ Previous"):
                st.session_state.page -= 1
                st.rerun()

    with col2:
        total_pages = (len(results) - 1) // page_size + 1
        st.markdown(f"<p style='text-align:center'>Page {st.session_state.page + 1} of {total_pages}</p>", unsafe_allow_html=True)

    with col3:
        if end < len(results):
            if st.button("Want more 🔽"):
                st.session_state.page += 1
                st.rerun()