"""
Utilities for extracting content from the GOV.UK knowledge graph from BigQuery.

Approach: pull the full edges table and the full nodes table in ONE query
each.

Usage:
    from google.cloud import bigquery
    client = bigquery.Client(project="govuk-knowledge-graph")

    edges_df = get_all_edges(
        "govuk-knowledge-graph.public.publishing_api_links_current", client
    )
    nodes_df = get_all_nodes(
        "govuk-knowledge-graph.public.publishing_api_editions_current", client,
        extra_columns=["document_type"],
    )
"""

import os
from collections.abc import Iterable

import pandas as pd
from google.cloud import bigquery

DEFAULT_PROJECT = "govuk-knowledge-graph"


def query_graph(
    query: str, client: bigquery.Client, job_config: bigquery.QueryJobConfig | None = None
) -> pd.DataFrame:
    return client.query(query, job_config=job_config).to_dataframe()


def estimate_bytes_processed(
    query: str,
    client: bigquery.Client,
    params: list[bigquery.ScalarQueryParameter | bigquery.ArrayQueryParameter] | None = None,
) -> int:
    """
    Run a dry-run query and return the number of bytes BigQuery estimates
    it would process. Dry-run queries are free and don't count against
    quota, so this is a safe way to estimate cost before running for real.
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=params or [], dry_run=True, use_query_cache=False
    )
    job = client.query(query, job_config=job_config)
    return job.total_bytes_processed


def get_all_edges(
    edges_table: str,
    client: bigquery.Client,
    columns: list[str] | None = None,
) -> pd.DataFrame:
    """
    Pull the entire edges table in one query.
    """
    cols = columns or [
        "source_content_id",
        "source_base_path",
        "target_content_id",
        "target_base_path",
        "type",
    ]
    query = f"SELECT {', '.join(cols)} FROM `{edges_table}`"
    return query_graph(query, client)


def get_all_nodes(
    nodes_table: str,
    client: bigquery.Client,
    columns: list[str] | None = None,
    extra_columns: list[str] | None = None,
    locale: str | None = "en",
) -> pd.DataFrame:
    """
    Pull the entire nodes table in one query (column-pruned to keep cost down).
    Same reasoning as get_all_edges: request only the columns you need.

    locale: publishing_api_editions_current has one row per (content_id, locale) —
        e.g. an "about" page has separate en and cy rows sharing the same content_id.
        Filtering to a single locale (default "en") restores one-row-per-content_id,
        which the rest of this pipeline assumes. Pass None to keep all locales
        (only do this if you intend to handle multiple rows per content_id yourself).
    """
    cols = columns or ["content_id", "base_path", "title", "description"]
    cols = cols + (extra_columns or [])
    query = f"SELECT {', '.join(cols)} FROM `{nodes_table}`"
    if locale is not None:
        query += " WHERE locale = @locale"
        job_config = bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("locale", "STRING", locale)]
        )
        return query_graph(query, client, job_config)
    return query_graph(query, client)


# query_knowledge_graph.py — updated get_node_metadata


def get_node_metadata(
    nodes_table: str,
    content_ids: Iterable[str],
    client: bigquery.Client,
    batch_size: int = 1000,
    extra_columns: list[str] | None = None,
    dry_run: bool = False,
) -> pd.DataFrame:
    """
    Fetch metadata (title, description, etc.) for a list of content_ids.

    dry_run: if True, estimates cost for every batch without executing any
        query (no rows returned — call again with dry_run=False once you're
        happy with the estimate). If False, runs for real and prints actual
        bytes processed/billed once complete.
    """
    ids = [c for c in dict.fromkeys(content_ids) if c]
    columns = ["content_id", "base_path", "title", "description"] + (extra_columns or [])
    select_cols = ",\n          ".join(columns)

    frames = []
    total_bytes_processed = 0
    total_bytes_billed = 0

    for i in range(0, len(ids), batch_size):
        batch = ids[i : i + batch_size]
        query = f"""
            SELECT
              {select_cols}
            FROM `{nodes_table}`
            WHERE content_id IN UNNEST(@ids)
        """
        params = [bigquery.ArrayQueryParameter("ids", "STRING", batch)]

        if dry_run:
            total_bytes_processed += estimate_bytes_processed(query, client, params)
            continue

        job_config = bigquery.QueryJobConfig(query_parameters=params)
        job = client.query(query, job_config=job_config)
        frames.append(job.to_dataframe())  # waits for completion — stats populated after
        total_bytes_processed += job.total_bytes_processed
        total_bytes_billed += job.total_bytes_billed

    if dry_run:
        print(
            f"Dry run: {total_bytes_processed / 1e9:.3f} GB would be processed "
            f"for {len(ids)} ids across {-(-len(ids) // batch_size)} batch(es)"
        )
        return pd.DataFrame(columns=columns)

    print(
        f"Processed {total_bytes_processed / 1e9:.3f} GB, "
        f"billed {total_bytes_billed / 1e9:.3f} GB, "
        f"for {len(ids)} ids across {len(frames)} batch(es)"
    )
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=columns)


if __name__ == "__main__":
    client = bigquery.Client(project=DEFAULT_PROJECT)

    EDGES_TABLE = "govuk-knowledge-graph.public.publishing_api_links_current"
    NODES_TABLE = "govuk-knowledge-graph.public.publishing_api_editions_current"
    OUTPUT_PATH = "data"

    # Two BigQuery queries total.
    edges_df = get_all_edges(EDGES_TABLE, client)
    print(f"Pulled {len(edges_df)} total edges from BigQuery")
    edges_df.to_csv(os.path.join(OUTPUT_PATH, "edges_df.csv"))

    nodes_df = get_all_nodes(NODES_TABLE, client, extra_columns=["document_type"])
    print(f"Pulled {len(nodes_df)} total nodes from BigQuery")
    nodes_df.to_csv(os.path.join(OUTPUT_PATH, "nodes_df.csv"))
