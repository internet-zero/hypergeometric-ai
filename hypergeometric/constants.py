"""Tunables and fixed strings shared across the pipeline."""

FILLER_SENTENCE = "This line is neutral placeholder text with no instruction content. "
DEFAULT_GENERATOR = "gpt-5.4-mini"
DEFAULT_THRESHOLD = 0.80
DEDUPE_SIMILARITY = 0.87
MAX_COMPLETION_TOKENS = 1600
CONCURRENCY = 8
RETRIES = 3
RAW_OUTPUT_MAX_CHARS = 4000  # per-response cap in raw.jsonl evidence records
RAW_ARGS_MAX_CHARS = 2000  # per-tool-call arguments cap in evidence records

PLANTED_REDUNDANT = "Always respond in English."
PLANTED_LOAD_BEARING = (
    'Always include a top-level field "marker" with the exact value "HG-7" '
    "in your JSON response."
)
