# Codex Integration Specs

## Status

This document is a specification and implementation plan only.

No runtime integration should be merged while this document is being reviewed.

Current intent:

- keep the existing Augment behavior unchanged
- plan a Codex integration that can feed the same charts when the metric semantics are truly compatible
- avoid inventing fake metadata or silently changing chart meaning

## Objective

Extend the dashboard so that Codex usage can be visualized alongside Augment usage on the same charts where the semantics match.

This must preserve the current Augment data model used by [data_loader.py](/Users/plambert/Documents/Work/augmentUsage/data_loader.py) and the current chart consumers in [app.py](/Users/plambert/Documents/Work/augmentUsage/app.py).

## Existing Constraints

### Current Augment Model

Today the dashboard assumes an additive dataframe with one row per Augment `token_usage` record.

The current chart pipeline expects at least these columns:

```python
[
    "session_id",
    "model_id",
    "created",
    "exchange_idx",
    "finished_at",
    "input_tokens",
    "output_tokens",
    "cache_read_input_tokens",
    "cache_creation_input_tokens",
    "system_prompt_tokens",
    "chat_history_tokens",
    "current_message_tokens",
    "max_context_tokens",
    "tool_definitions_tokens",
    "tool_result_tokens",
    "assistant_response_tokens",
]
```

The existing app logic then derives:

- totals by summing token columns
- per-session summaries by grouping on `session_id`
- time charts by grouping on `finished_at`
- model charts by grouping on `model_id`
- cost charts through `compute_cost()`

### Current Codex Reality

Codex sessions are JSONL event streams, not a single session JSON document.

Observed event types:

- `session_meta`
- `task_started`
- `task_complete`
- `turn_context`
- `user_message`
- `agent_message`
- `token_count`
- `function_call`
- `function_call_output`
- `turn_aborted`

Observed token payload:

```json
{
  "total_token_usage": {
    "input_tokens": 136487,
    "cached_input_tokens": 103936,
    "output_tokens": 2122,
    "reasoning_output_tokens": 1121,
    "total_tokens": 138609
  },
  "last_token_usage": {
    "input_tokens": 37519,
    "cached_input_tokens": 37248,
    "output_tokens": 261,
    "reasoning_output_tokens": 56,
    "total_tokens": 37780
  },
  "model_context_window": 258400
}
```

## Non-Negotiable Aggregation Rule

Codex must be aggregated on the same additive model as Augment.

That means:

- each Codex row used by charts must represent a true additive increment
- summing all Codex rows in a session must reproduce the session totals exactly

### Why Raw `last_token_usage` Is Unsafe

Observed Codex logs contain repeated `token_count` snapshots.

Consequence:

- summing `last_token_usage` across all `token_count` events can overcount

### Canonical Rule

The Codex additive unit must be derived from deduplicated cumulative totals:

1. read all `token_count` events where `payload.info` is non-null
2. order them by event timestamp
3. use `total_token_usage` as the source of truth
4. drop consecutive duplicate cumulative snapshots
5. compute the delta between each accepted snapshot and the previous accepted snapshot
6. emit one additive Codex row per delta

This is the only approach that matches the existing Augment accounting model.

### Aggregation Pseudocode

```python
accepted = []

for snapshot in snapshots_sorted_by_timestamp:
    if not accepted:
        accepted.append(snapshot)
        continue
    if snapshot.cumulative_key != accepted[-1].cumulative_key:
        accepted.append(snapshot)

deltas = []
prev = None
for snapshot in accepted:
    if prev is None:
        delta = snapshot.total_usage
    else:
        delta = snapshot.total_usage - prev.total_usage
    deltas.append(delta)
    prev = snapshot
```

## Field Mapping

### Fields That Can Be Mapped Directly

These Codex metrics are semantically compatible with current Augment charts:

- Codex `input_tokens` -> dashboard `input_tokens`
- Codex `output_tokens` -> dashboard `output_tokens`
- Codex `cached_input_tokens` -> dashboard `cache_read_input_tokens`
- Codex `model_context_window` -> dashboard `max_context_tokens`

### Fields That Must Stay Separate

These must not be folded silently into existing Augment fields:

- Codex `reasoning_output_tokens`
- Codex `total_tokens`
- Codex `model_provider`
- Codex workspace metadata such as `cwd`

### Important Invariant

Observed in local Codex logs:

- `total_tokens = input_tokens + output_tokens`
- `cached_input_tokens` is not part of `total_tokens`
- `reasoning_output_tokens` is not part of `total_tokens`

Therefore:

- common charts should continue using `input_tokens + output_tokens` as active total
- cached tokens remain a separate metric
- reasoning output becomes a Codex-specific supplemental metric

## Target Data Model

The eventual target is a normalized usage dataframe that still preserves the current Augment columns.

### Required Shared Columns

These are the columns that must exist for both Augment and Codex rows:

```python
SHARED_USAGE_COLUMNS = [
    "session_id",
    "model_id",
    "created",
    "exchange_idx",
    "finished_at",
    "input_tokens",
    "output_tokens",
    "cache_read_input_tokens",
    "cache_creation_input_tokens",
    "system_prompt_tokens",
    "chat_history_tokens",
    "current_message_tokens",
    "max_context_tokens",
    "tool_definitions_tokens",
    "tool_result_tokens",
    "assistant_response_tokens",
]
```

### Required Metadata Columns

These should be added for source-awareness and gating:

```python
NORMALIZED_METADATA_COLUMNS = [
    "source",
    "model_provider",
    "cwd",
    "originator",
    "cli_version",
    "client_source",
    "plan_type",
    "turn_id",
    "reasoning_output_tokens",
    "total_tokens",
    "model_context_window",
    "supports_cost",
    "supports_token_breakdown",
    "supports_precise_model_id",
]
```

### Source Rules

For Augment rows:

- `source = "augment"`
- `supports_cost = True`
- `supports_token_breakdown = True`
- `supports_precise_model_id = True`

For Codex rows:

- `source = "codex"`
- `supports_cost = False`
- `supports_token_breakdown = False`
- `supports_precise_model_id = False` unless a real model id is later discovered

## Chart Compatibility Matrix

### Safe To Combine In V1

These charts can use combined Augment + Codex rows once the shared schema exists:

- summary cards for sessions, exchanges, input, output, cache
- token usage over time
- top sessions by token usage
- cache efficiency
- hourly activity heatmap
- context window utilization
- token efficiency ratio based on output/input
- session duration distribution
- daily or weekly token totals
- tool usage, if tool extraction is normalized too

### Must Stay Metadata-Gated

These should not include Codex rows in the first rollout:

- cost cards
- cost over time
- cost by model
- daily burn rate
- model comparison by cost
- detailed token breakdown using prompt/history/tool subtokens

### Potentially Misleading If Combined Naively

These require a decision before inclusion:

- model pie chart
  Reason:
  Codex currently exposes `model_provider`, not a precise model id.

- detailed session tables with cost and prompt breakdown
  Reason:
  Codex does not currently expose all of the same subfields.

## Step-By-Step Implementation Plan

### Step 1: Introduce a Normalized Schema in `data_loader.py`

Goal:

- define the shared dataframe contract without changing the current Augment behavior yet

Planned work:

- create a normalized column list
- create helpers to backfill missing metadata columns with defaults
- leave `load_sessions()` behavior unchanged except for optional metadata enrichment

Planned snippet:

```python
NORMALIZED_COLUMNS = SHARED_USAGE_COLUMNS + NORMALIZED_METADATA_COLUMNS

def _normalize_usage_df(df: pd.DataFrame) -> pd.DataFrame:
    for col in NORMALIZED_COLUMNS:
        if col not in df.columns:
            df[col] = DEFAULTS.get(col)
    return df[NORMALIZED_COLUMNS]
```

Acceptance criteria:

- existing Augment loader still returns rows consumable by the current app
- no chart code has been changed yet

### Step 2: Add a Codex Raw Reader

Goal:

- parse `.jsonl` files into structured event objects

Planned work:

- read `session_meta`
- collect `token_count`
- collect `function_call`
- collect `task_started`, `task_complete`, `turn_context`

Planned snippet:

```python
def iter_codex_events(path: Path) -> Iterator[dict]:
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)
```

Acceptance criteria:

- malformed lines are skipped with warnings
- a session with no token data does not crash parsing

### Step 3: Build Codex Cumulative Snapshots

Goal:

- isolate only the cumulative token snapshots needed for additive reconstruction

Planned work:

- extract `payload.info.total_token_usage`
- store timestamp
- store `turn_id`
- store `plan_type`
- store `model_context_window`

Planned snippet:

```python
snapshot = {
    "timestamp": event["timestamp"],
    "turn_id": current_turn_id,
    "plan_type": rate_limits.get("plan_type"),
    "input_tokens": total_usage.get("input_tokens", 0),
    "cache_read_input_tokens": total_usage.get("cached_input_tokens", 0),
    "output_tokens": total_usage.get("output_tokens", 0),
    "reasoning_output_tokens": total_usage.get("reasoning_output_tokens", 0),
    "total_tokens": total_usage.get("total_tokens", 0),
    "model_context_window": info.get("model_context_window", 0),
}
```

Acceptance criteria:

- snapshots are sorted by timestamp
- duplicate cumulative snapshots can be identified deterministically

### Step 4: Reconstruct Additive Codex Rows

Goal:

- produce Codex rows that behave exactly like Augment additive rows

Planned work:

- deduplicate repeated cumulative snapshots
- compute deltas between accepted snapshots
- reject non-monotonic sessions or rows with negative deltas

Planned snippet:

```python
delta_input = current["input_tokens"] - previous["input_tokens"]
delta_cache = current["cache_read_input_tokens"] - previous["cache_read_input_tokens"]
delta_output = current["output_tokens"] - previous["output_tokens"]
delta_reasoning = current["reasoning_output_tokens"] - previous["reasoning_output_tokens"]
delta_total = current["total_tokens"] - previous["total_tokens"]
```

Acceptance criteria:

- sum of Codex delta rows equals final cumulative totals for the session
- duplicate `token_count` events do not add extra usage

### Step 5: Map Codex Rows Onto the Shared Schema

Goal:

- make Codex rows consumable by the same chart code as Augment where possible

Planned mapping:

```python
row = {
    "session_id": session_id,
    "model_id": fallback_model_id,
    "created": created_at,
    "exchange_idx": event_idx,
    "finished_at": snapshot_timestamp,
    "input_tokens": delta_input,
    "output_tokens": delta_output,
    "cache_read_input_tokens": delta_cache,
    "cache_creation_input_tokens": 0,
    "system_prompt_tokens": 0,
    "chat_history_tokens": 0,
    "current_message_tokens": 0,
    "max_context_tokens": model_context_window,
    "tool_definitions_tokens": 0,
    "tool_result_tokens": 0,
    "assistant_response_tokens": delta_output,
    "source": "codex",
    "model_provider": model_provider,
    "cwd": cwd,
    "reasoning_output_tokens": delta_reasoning,
    "total_tokens": delta_total,
    "supports_cost": False,
    "supports_token_breakdown": False,
    "supports_precise_model_id": False,
}
```

Important note:

- the fallback `model_id` must be obviously synthetic, for example `codex-openai`
- it must never pretend to be a precise model name

Acceptance criteria:

- Codex rows can be concatenated with Augment rows
- common grouping logic still works on `session_id`, `finished_at`, and token columns

### Step 6: Add Combined Loader Functions

Goal:

- make combined chart feeding explicit and easy to reason about

Planned function signatures:

```python
def load_codex_usage(sessions_dir: str | None = None) -> pd.DataFrame: ...

def load_combined_usage(
    augment_sessions_dir: str | None = None,
    codex_sessions_dir: str | None = None,
    include_augment: bool = True,
    include_codex: bool = True,
) -> pd.DataFrame: ...
```

Planned behavior:

- `load_codex_usage()` returns only normalized Codex additive rows
- `load_combined_usage()` concatenates normalized Augment and Codex rows
- both outputs are sorted by `finished_at`

Acceptance criteria:

- calling combined loader with `include_codex=False` behaves like current Augment-only flow

### Step 7: Normalize Tool Usage

Goal:

- allow the tool usage chart to combine both sources

Planned work:

- keep current Augment `extract_tool_usage()`
- add a Codex extractor over `function_call`
- concatenate the two with a `source` column

Planned snippet:

```python
tool_row = {
    "session_id": session_id,
    "tool_name": payload.get("name", "unknown"),
    "count": 1,
    "source": "codex",
}
```

Acceptance criteria:

- top tools chart can split by `source` or aggregate both

### Step 8: Wire the App in Two Passes

Goal:

- reduce regression risk by changing app consumers gradually

#### Pass 8A: Replace Only the Common Loader Input

Planned change:

- update `_load_and_prepare()` to optionally load combined usage rows
- keep chart code identical at first

Planned snippet:

```python
def _load_and_prepare() -> tuple[pd.DataFrame, dict, pd.DataFrame]:
    df = load_combined_usage()
    pricing = fetch_pricing()
    tool_df = extract_combined_tool_usage()
    ...
```

Guardrails:

- do not include Codex rows in cost calculations
- do not include Codex rows in prompt breakdown charts yet

#### Pass 8B: Add Source-Aware Filtering and Gating

Planned change:

- add a `source` filter in the UI
- branch charts only where needed

Planned snippet:

```python
cost_df = dff[dff["supports_cost"]]
breakdown_df = dff[dff["supports_token_breakdown"]]
common_df = dff
```

Acceptance criteria:

- existing Augment visuals still render correctly
- Codex rows appear only in charts that are semantically safe

### Step 9: Update Chart Logic Chart-By-Chart

Goal:

- explicitly decide inclusion rules instead of relying on accidental compatibility

#### Combine Immediately

Use `common_df`:

- cards for sessions, exchanges, input, output, cache
- token-over-time
- session totals
- cache efficiency
- heatmap
- context window
- efficiency ratio
- duration distribution
- daily and weekly token totals
- tool usage

#### Gate To Augment Only

Use `cost_df` or `breakdown_df`:

- cost cards and charts
- model comparison by cost
- token breakdown stacked bar

#### Pending Design Decision

- model pie
- mixed-source session tables
- export/import schema

### Step 10: Add Validation

Goal:

- prove Codex rows are additive and safe to mix with Augment rows

Required validations:

```python
assert deltas["input_tokens"].sum() == final_snapshot["input_tokens"]
assert deltas["cache_read_input_tokens"].sum() == final_snapshot["cache_read_input_tokens"]
assert deltas["output_tokens"].sum() == final_snapshot["output_tokens"]
assert deltas["reasoning_output_tokens"].sum() == final_snapshot["reasoning_output_tokens"]
assert deltas["total_tokens"].sum() == final_snapshot["total_tokens"]
```

Required structural checks:

- cumulative totals never decrease
- duplicate snapshots do not produce extra deltas
- empty sessions do not crash
- `turn_aborted` sessions still produce partial valid totals

### Step 11: Add Tests

Minimum fixtures:

1. a Codex session with unique snapshots
2. a Codex session with duplicate `token_count`
3. a Codex session with null `payload.info`
4. a Codex session with tools but no token data
5. a Codex session with `turn_aborted`
6. a mixed Augment + Codex combined load

Suggested test shape:

```python
def test_codex_deltas_match_final_totals():
    df = load_codex_usage(sample_dir)
    assert df["input_tokens"].sum() == EXPECTED_INPUT
```

## Rollout Order

Recommended implementation order:

1. schema helpers
2. Codex raw reader
3. cumulative snapshot extraction
4. additive delta reconstruction
5. Codex row mapping
6. combined loader
7. combined tool loader
8. loader unit tests
9. app wiring for common charts
10. source-aware chart gating
11. export/import redesign if still needed

## Explicit Non-Goals For The First Implementation Pass

- no pricing estimation for Codex
- no fake Codex prompt breakdown
- no fake precise model names for Codex
- no team export format changes until a versioned schema is designed
- no silent inclusion of Codex rows in cost charts

## Open Questions

Questions to answer before implementation starts:

1. Do we want the default dashboard view to show combined sources, or keep a source filter defaulted to `augment` first?
2. Should the model pie chart hide Codex rows entirely until a true model id exists?
3. Should `reasoning_output_tokens` get its own card in the shared header, or live only in Codex-specific sections?
4. Do we want combined tables to display a `source` column by default?

## Decision Summary

The key design decision is:

- Codex integration must produce additive rows that match the Augment accounting model

The key implementation decision is:

- derive those rows from deduplicated cumulative `total_token_usage` snapshots, not from raw `last_token_usage`

The key rollout decision is:

- combine only semantically compatible charts first, and gate the rest through explicit metadata instead of approximation
