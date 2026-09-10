"""
build_subgraph.py — end-to-end run for a given life event.

Prerequisites:
  - edges_df and nodes_df already pulled via query_knowledge_graph.py's
    get_all_edges / get_all_nodes and saved to data/edges_df.csv,
    data/nodes_df.csv (no 'details' column needed at this stage).
  - A BigQuery client with access to govuk-knowledge-graph, for the final
    targeted 'details' enrichment step only.

For a given life event, specify:
- LIFE_EVENT - preferably consistent with service-graph life event naming
- START_CONTENT_ID - content ID for the mainstream_browse_page where to start crawling from
- OUTPUT_PATH
- KNOWN_PATHS from service-graph to compare to

Note on --dry-run mode:
This mode was implemented to control costs associated with enriching basic node info
with metadata from `details` column in `govuk-knowledge-graph.public.publishing_api_editions_current`
table. Adding metadata drastically increases amount of data processed as `details` contains a lot
of content.

Usage:
python build_subgraph.py --dry-run   # prints the bytes-processed estimate, writes nothing
python build_subgraph.py             # runs for real, writes data/driving_subgraph.json
"""

import argparse
import json

import pandas as pd
from google.cloud import bigquery
from graph_crawler import build_life_event_subgraph, compare_to_known_paths
from query_knowledge_graph import get_node_metadata

EDGES_CSV = "data/edges_df.csv"
NODES_CSV = "data/nodes_df.csv"
OUTPUT_PATH = "data/having_a_baby_subgraph.json"
NODES_TABLE = "govuk-knowledge-graph.public.publishing_api_editions_current"

LIFE_EVENT = "baby"

START_CONTENT_ID = (
    "6028e11b-592e-40ec-81e6-312c9fcb749d"  # /browse/childcare-parenting/pregnancy-birth
)
# START_CONTENT_ID_DRIVING = "6af0f337-4da6-415c-a760-55b612d0e3e3"  # /browse/driving/learning-to-drive

KNOWN_PATHS = {
    "/register-birth",  # gro-register-birth
    "/order-copy-birth-death-marriage-certificate",  # gro-certificates
    "/paternity-pay-leave",  # hmrc-spp
    "/maternity-pay-leave/pay",  # hmrc-smp
    "/maternity-allowance",  # dwp-maternity-allowance
    "/sure-start-maternity-grant",  # dwp-sure-start-grant
    "/request-baby-loss-certificate",  # dhsc-baby-loss-certificate
}
# KNOWN_PATHS = {
#     "/apply-first-provisional-driving-licence",  # dvla-provisional-licence
#     "/sold-bought-vehicle",  # dvla-vehicle-sale
#     "/make-a-sorn",  # dvla-sorn
#     "/vehicle-tax",  # dvla-vehicle-tax
#     "/book-driving-test",  # dvsa-driving-test
#     "/book-theory-test",  # dvsa-theory-test
#     "/clean-air-zones",  # jaqu-clean-air-zone
# }


def main(dry_run: bool = False) -> None:
    edges_df = pd.read_csv(EDGES_CSV)
    nodes_df = pd.read_csv(NODES_CSV)  # no 'details' yet — enriched at the end, targeted only

    pruned_nodes_df, pruned_edges_df = build_life_event_subgraph(
        START_CONTENT_ID,
        edges_df,
        nodes_df,
    )

    # Targeted 'details' pull for the final (small) node set only — not the
    # whole table. Run with --dry-run first if this is your first time
    # hitting 'details' for a given table/project, to check the cost.
    client = bigquery.Client(project="govuk-knowledge-graph")

    detail_df = get_node_metadata(
        NODES_TABLE,
        pruned_nodes_df["content_id"].tolist(),
        client,
        extra_columns=["document_type", "details"],
        dry_run=dry_run,
    )

    if dry_run:
        return

    output = {
        "life_event": LIFE_EVENT,
        "nodes": detail_df.to_dict("records"),
        "edges": pruned_edges_df.to_dict("records"),
    }
    with open(OUTPUT_PATH, "w") as f:
        json.dump(output, f, indent=2, default=str)

    print(f"Wrote {len(detail_df)} nodes, {len(pruned_edges_df)} edges -> {OUTPUT_PATH}")

    comparison = compare_to_known_paths(pruned_nodes_df=pruned_nodes_df, known_paths=KNOWN_PATHS)
    print(f"Comparison to service-graph: {comparison}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build a life-event subgraph end to end.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Estimate bytes processed for the 'details' enrichment step instead of "
        "actually running it — no JSON output is written.",
    )
    args = parser.parse_args()
    main(dry_run=args.dry_run)
