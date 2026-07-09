from src.ground_truth import GROUND_TRUTH, GROUND_TRUTH_TITLES, RESOLUTION_NOTES, UNRESOLVED_TITLES
from src.recommender import anime_df, get_results, movies_df, recommend


def recommendation_catalog_ids():
    movie_ids = set(movies_df["id"].astype(str).tolist())
    anime_ids = {f"anime_{id_}" for id_ in anime_df["myanimelist_id"].astype(str).tolist()}
    return movie_ids | anime_ids


def compute_metrics(ground_truth=None, top_k=10):
    ground_truth = ground_truth or GROUND_TRUTH
    per_query = []
    available_ids = recommendation_catalog_ids()
    out_of_catalog = []

    for query, relevant_ids in ground_truth.items():
        relevant = set(relevant_ids)
        missing_from_catalog = [title_id for title_id in relevant_ids if title_id not in available_ids]
        out_of_catalog.extend([
            {
                "query": query,
                "id": title_id,
                "title": GROUND_TRUTH_TITLES.get(query, {}).get(title_id, title_id),
            }
            for title_id in missing_from_catalog
        ])

        # Titles that are actually in the recommender's catalog. Out-of-catalog
        # relevant titles can never be retrieved, so we exclude them from the
        # denominators (they'd only re-impose an artificial ceiling) and surface
        # them separately in the honesty panel instead.
        in_catalog_relevant = [tid for tid in relevant_ids if tid not in missing_from_catalog]
        r = len(in_catalog_relevant)

        # Evaluate the base recommender without relevance feedback, so ad-hoc
        # like/dislike clicks during testing or a live demo can't skew the metrics.
        top_indices, final_scores, all_ids = recommend(
            query, content_filter="all", top_n=top_k, use_feedback=False
        )
        results = get_results(top_indices, final_scores, all_ids)
        retrieved_ids = [result["id"] for result in results[:top_k]]
        retrieved = set(retrieved_ids)
        hits = [title_id for title_id in retrieved_ids if title_id in relevant]

        # Precision@R: of the top-R results (R = number of reachable relevant titles),
        # how many are correct. Its ceiling is 100%, unlike Precision@10 which is
        # capped at R/10 whenever a query has fewer than 10 relevant titles.
        hits_at_r = [tid for tid in retrieved_ids[:r] if tid in relevant]

        precision_at_10 = len(hits) / top_k if top_k else 0
        precision_at_r = len(hits_at_r) / r if r else 0
        recall_at_10 = len(hits) / r if r else 0
        f1 = (
            2 * precision_at_r * recall_at_10 / (precision_at_r + recall_at_10)
            if precision_at_r + recall_at_10
            else 0
        )

        per_query.append({
            "query": query,
            "top_k": top_k,
            "r": r,
            "precision": round(precision_at_10, 4),
            "precision_at_r": round(precision_at_r, 4),
            "recall": round(recall_at_10, 4),
            "f1": round(f1, 4),
            "hits": hits,
            "hit_count": len(hits),
            "relevant_ids": relevant_ids,
            "relevant_titles": GROUND_TRUTH_TITLES.get(query, {}),
            "retrieved_ids": retrieved_ids,
            "retrieved_titles": {
                result["id"]: result["title"]
                for result in results[:top_k]
            },
            "missed_ids": [title_id for title_id in in_catalog_relevant if title_id not in retrieved],
            "out_of_catalog_ids": missing_from_catalog,
        })

    count = len(per_query)
    aggregate = {
        "mean_precision": round(sum(item["precision"] for item in per_query) / count, 4) if count else 0,
        "mean_precision_at_r": round(sum(item["precision_at_r"] for item in per_query) / count, 4) if count else 0,
        "mean_recall": round(sum(item["recall"] for item in per_query) / count, 4) if count else 0,
        "mean_f1": round(sum(item["f1"] for item in per_query) / count, 4) if count else 0,
        "query_count": count,
        "top_k": top_k,
    }

    return {
        "aggregate": aggregate,
        "per_query": per_query,
        "resolution_notes": RESOLUTION_NOTES,
        "unresolved_titles": UNRESOLVED_TITLES,
        "out_of_catalog": out_of_catalog,
    }
