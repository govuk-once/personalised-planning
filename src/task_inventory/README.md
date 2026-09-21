# src/task_inventory

Extracts structured citizen-task records from GOV.UK page content.  The pipeline
reads a subgraph of GOV.UK pages, finds actionable sentences, drafts task objects
with an LLM, and reconciles them into a deduplicated task inventory.

Orchestrated end-to-end by **`scripts/task_inventory/run_pipeline.py`**.

---

## Pipeline stages and files

| Stage | File(s) | What it does | Inputs | Outputs |
|-------|---------|--------------|--------|---------|
| 0-1 | `sections.py` | Parses GOV.UK pages into per-sentence rows | `data/having_a_baby_subgraph.json` | `data/sentences.csv` |
| 2 | `candidates.py` | Flags action/deadline candidates via pattern matching + LLM | `data/sentences.csv` | `data/candidates.csv` |
| 3 | `drafts.py` | One LLM call per section → structured Draft objects | `data/sentences_extracted.csv`, `data/candidates.csv`, `prompts/section_drafts.v2.md` | `data/runs/latest/drafts.jsonl`, `drafts_rejected.jsonl`, `stage3_summary.json` |
| 4a | `reconcile/blocking.py` | Near-duplicate pre-merge + policy-family grouping | Draft list | Groups of drafts (in memory) |
| 4b | `reconcile/clustering.py` | LLM assigns drafts to clusters within each group | Groups, `prompts/clusters.v2.md` | `ClusterResult` objects |
| 4c | `reconcile/merge.py` | Deterministic field-level merge of each cluster | Clusters + Draft lookup | `TaskRecord` objects |
| 5 | `checks.py` | Semantic validation of drafts and tasks | Draft / TaskRecord objects | Error + warning lists |
| 5 | `review.py` | CSV snapshots for human review gates | Drafts, clusters, conflicts | `drafts_review.csv`, `clusters.csv`, `conflicts.csv` |
| 5 | `reports.py` | Markdown run reports | Counts, drafts, tasks | `funnel.md`, `validation.md`, `coverage.md`, `diff.md` |

Supporting files:

| File | Role |
|------|------|
| `schema.py` | All Pydantic models (`Draft`, `TaskRecord`, etc.) and vocabulary types; no I/O |
| `llm.py` | Shared Bedrock call helper with caching, normalisation, and retries |
| `__init__.py` | Re-exports the public API (models + stage functions) |
| `reconcile/__init__.py` | Re-exports the four reconcile functions |

---

## How scripts/task_inventory/run_pipeline.py uses these modules

```
scripts/task_inventory/run_pipeline.py
│
├── Stage 0-1  sections.extract_sections_from_subgraph()
├── Stage 2    candidates.flag_candidates_from_sentences()
├── Stage 3    drafts.run_section_drafts()
│               └── calls llm.call_structured() per section
│               └── calls checks.check_draft() per draft
│
├── Stage 4    (reconcile sub-package)
│   ├── 4a  reconcile.blocking.premerge_near_duplicates()
│   ├── 4a  reconcile.blocking.group_drafts()
│   ├── 4b  reconcile.clustering.cluster_group()   [one call per group]
│   ├── 4b  reconcile.clustering.enforce_exactly_once()
│   ├── 4b  reconcile.clustering.expand_followers()
│   └── 4c  reconcile.merge.merge_cluster()         [one call per cluster]
│
└── Stage 5
    ├── checks.check_task() + check_task_ids_unique()
    ├── review.generate_drafts_review_csv()
    ├── review.generate_clusters_csv()
    ├── review.generate_conflicts_csv()
    ├── reports.generate_funnel_report()
    ├── reports.generate_validation_report()
    ├── reports.generate_coverage_report()
    └── reports.generate_diff_report()
```

### Running the full pipeline

```bash
# From the project root (sets PYTHONPATH so src.* imports resolve):
python scripts/task_inventory/run_pipeline.py \
  --subgraph data/having_a_baby_subgraph.json \
  --sentences data/sentences.csv \
  --candidates data/candidates.csv \
  --output data/runs/$(date +%Y%m%d)

# Run a single stage (e.g. after editing candidates.csv):
python scripts/task_inventory/run_pipeline.py --stage drafts
python scripts/task_inventory/run_pipeline.py --stage reconcile
python scripts/task_inventory/run_pipeline.py --stage report
```

### Environment requirements

- **AWS credentials** in the environment (e.g. `aws-vault exec <profile> -- python ...`).
- `ANTHROPIC_MODEL` — Bedrock model ID (default `eu.anthropic.claude-sonnet-5`).
- `AWS_REGION` — AWS region (default `eu-west-2`).

### LLM call cache

Stages 3 and 4b write JSON cache files under `data/cache/`.  Delete this
directory (or specific subdirectories `drafts/` / `clusters/`) to force LLM
calls to re-run.  Cache keys include the model ID and prompt version, so
upgrading either automatically invalidates the cache.
