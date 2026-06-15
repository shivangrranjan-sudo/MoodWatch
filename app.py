import streamlit as st
import re
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from src.preprocessing import clean_text

titles = ["Your Name", "Attack on Titan", "Spirited Away", "Death Note"]
raw_descriptions = [
    "A heartwarming romantic story about two teenagers swapping bodies and falling in love.",
    "A dark intense action series about humanity fighting giant monsters and survival.",
    "A magical adventure about a girl trapped in a spirit world full of wonder.",
    "A dark psychological thriller about a genius using a notebook to kill criminals.",
]

cleaned_descriptions = [clean_text(desc) for desc in raw_descriptions]

st.set_page_config(page_title="MoodWatch Phase 0", layout="centered")
st.title("🎬 MoodWatch ")

query = st.text_input("Enter your mood or vibe:", value="something dark and intense")

if query:
    cleaned_query = clean_text(query)
    
    vectorizer = TfidfVectorizer()
    all_text = cleaned_descriptions + [cleaned_query]
    tfidf_matrix = vectorizer.fit_transform(all_text)
    
    query_vec = tfidf_matrix[-1]  
    doc_vecs = tfidf_matrix[:-1]   
    
    scores = cosine_similarity(query_vec, doc_vecs)[0]
    
    ranked_results = sorted(zip(titles, scores, raw_descriptions), key=lambda x: x[1], reverse=True)
    top_title, top_score, top_desc = ranked_results[0]
    
    st.write("---")
    st.subheader("🎯 Top Match Recommendation")
    
    col1, col2 = st.columns([1, 3])
    
    with col1:
        st.image("https://via.placeholder.com/150x220?text=Poster", use_container_width=True)
        
    with col2:
        st.markdown(f"### {top_title} <span style='color:#2ecc71; font-size:18px;'>({top_score*100:.1f}% Match)</span>", unsafe_allow_html=True)
        st.caption("✨ Type: Anime  ·  📅 Year: 2013  ·  ⏱️ Runtime: 24m/ep")
        st.write(top_desc)
        
        st.markdown("**Streaming on:** 🟢 Crunchyroll | 🔴 Netflix")
        
        st.info(f"📊 **Scores Debug:** TF-IDF: `{top_score:.4f}` | Sentiment: `N/A ` | Final Score: `{top_score:.4f}`")
        
        btn_col1, btn_col2 = st.columns([1, 5])
        with btn_col1:
            st.button("👍")
        with btn_col2:
            st.button("👎")