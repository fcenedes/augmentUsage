# Codex Usage Integration Spec

## Goal

Add Codex usage data to the dashboard without changing or regressing the existing Augment behavior.

The existing Augment pipeline must remain intact:

- `load_sessions()` in [data_loader.py](/Users/plambert/Documents/Work/augmentUsage/data_loader.py)
- `extract_tool_usage()` in [data_loader.py](/Users/plambert/Documents/Work/augmentUsage/data_loader.py)
- `_load_and_prepare()` and all current `df / pricing / tool_df` consumers in [app.py](/Users/plambert/Documents/Work/augmentUsage/app.py)

The Codex integration must be additive only:

- new loader(s)
- new dataframes
- new UI section/tab(s)
- no behavior change in current Augment views

## Source Data

Codex sessions are stored as JSONL event streams under paths like:

- `/Users/plambert/.codex/sessions/2026/03/24/rollout-2026-03-24T12-15-14-019d1f8e-5504-7481-b214-757f70c5b63c.jsonl`

Observed event types include:

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

Important difference versus Augment:

- Augment stores session data as one JSON document with explicit `token_usage` records on response nodes.
- Codex stores a chronological event log and exposes token usage through repeated `token_count` snapshots.

## Existing Augment Aggregation Model

Today, Augment token usage is additive at the row level:

1. `load_sessions()` emits one dataframe row per `response_node.token_usage`.
2. Each row contains token fields such as `input_tokens`, `output_tokens`, `cache_read_input_tokens`, and `cache_creation_input_tokens`.
3. Dashboard totals are simple sums over those per-row fields.
4. Session totals are sums of all rows sharing the same `session_id`.

This is the model Codex must match.

For Codex, we therefore need an equivalent additive unit. The correct unit is not the raw JSONL line and not the raw `token_count` event as-is. We must derive additive delta rows from the cumulative token snapshots.

## Critical Aggregation Rule

### Problem

Codex `token_count` events are cumulative snapshots, not guaranteed unique deltas.

Observed on local samples:

- `total_token_usage` is monotonic non-decreasing within a session.
- duplicate snapshots occur in the same session.
- some duplicate snapshots repeat the same totals with zero real increment.

Example consequence:

- summing raw `last_token_usage` over all `token_count` events overcounts session totals.

This means the naive approach is wrong:

- wrong: `sum(last_token_usage.*)` across all `token_count` events

### Correct Rule

For Codex, the canonical additive unit must be computed as:

1. Read all `token_count` events with non-null `payload.info`.
2. Order them by event timestamp.
3. Use `total_token_usage` as the source of truth.
4. Drop consecutive duplicate cumulative snapshots.
5. Compute per-event deltas from the accepted cumulative sequence.
6. Treat each delta as the Codex equivalent of one Augment `token_usage` row.

This gives the same additive behavior as Augment:

- session total = sum of additive rows
- period total = sum of additive rows
- chart series = aggregate additive rows over time

### Why `total_token_usage`, Not `last_token_usage`

`last_token_usage` looks like a delta, but duplicate `token_count` events can replay the same delta again.

`total_token_usage` is safer because:

- it is monotonic in the observed data
- duplicate snapshots can be deduplicated reliably
- deltas can be reconstructed exactly from cumulative totals

## Token Field Mapping

Codex exposes these token families in observed logs:

- `input_tokens`
- `cached_input_tokens`
- `output_tokens`
- `reasoning_output_tokens`
- `total_tokens`
- `model_context_window`

### Mapping to Existing Dashboard Semantics

To stay aligned with Augment:

- Augment `input_tokens` maps to Codex `input_tokens`
- Augment `output_tokens` maps to Codex `output_tokens`
- Augment `cache_read_input_tokens` maps to Codex `cached_input_tokens`

Do not remap or merge these:

- Codex `reasoning_output_tokens` must remain separate
- Codex `total_tokens` must not replace `input_tokens + output_tokens` blindly in existing charts

### Important Observed Invariant

In the sampled Codex logs:

- `total_tokens = input_tokens + output_tokens`
- `cached_input_tokens` is not included in `total_tokens`
- `reasoning_output_tokens` is not included in `total_tokens`

Therefore:

- existing Augment-style "total active tokens" semantics should remain `input + output`
- cached tokens must be charted separately
- reasoning tokens should be exposed in Codex-specific cards/charts, not folded into output unless explicitly decided later

## Canonical Codex Aggregation Algorithm

For each `.jsonl` file:

1. Read `session_meta`
   - extract `session_id`
   - extract session start timestamp
   - extract `cwd`
   - extract `originator`
   - extract `cli_version`
   - extract `source`
   - extract `model_provider`

2. Read all `token_count` events with non-null `payload.info`
   - parse event timestamp
   - collect cumulative snapshot:
     - `input_tokens`
     - `cached_input_tokens`
     - `output_tokens`
     - `reasoning_output_tokens`
     - `total_tokens`
     - `model_context_window`

3. Sort snapshots by timestamp

4. Deduplicate consecutive identical cumulative snapshots
   - duplicate key:
     - `input_tokens`
     - `cached_input_tokens`
     - `output_tokens`
     - `reasoning_output_tokens`
     - `total_tokens`

5. Derive additive delta rows
   - first accepted snapshot:
     - delta = cumulative snapshot itself
   - each next accepted snapshot:
     - delta = current cumulative - previous cumulative

6. Validate each delta
   - no negative values
   - `delta_total_tokens == delta_input_tokens + delta_output_tokens`
   - if invalid, log warning and skip or quarantine the row

7. Emit one Codex usage row per accepted delta

### Pseudocode

```text
accepted = []
for snapshot in token_count_snapshots_sorted:
    if accepted is empty:
        accepted.append(snapshot)
    else if snapshot.cumulative_key != accepted[-1].cumulative_key:
        accepted.append(snapshot)

deltas = []
for i, snapshot in enumerate(accepted):
    if i == 0:
        delta = snapshot.total
    else:
        delta = snapshot.total - accepted[i - 1].total
    deltas.append(delta)
```

## Required Dataframes

### 1. `codex_usage_df`

Purpose:

- additive dataframe equivalent to Augment `df`

One row per derived Codex token delta.

Required columns:

- `source` = `codex`
- `session_id`
- `created`
- `finished_at`
- `event_idx`
- `cwd`
- `model_provider`
- `input_tokens`
- `cached_input_tokens`
- `output_tokens`
- `reasoning_output_tokens`
- `total_tokens`
- `model_context_window`

Optional but useful:

- `turn_id`
- `plan_type`
- `originator`
- `cli_version`

### 2. `codex_sessions_df`

Purpose:

- session-level summaries for cards, tables, workspace views

One row per Codex session.

Required columns:

- `session_id`
- `created`
- `finished_at`
- `cwd`
- `model_provider`
- `session_duration_sec`
- `input_tokens`
- `cached_input_tokens`
- `output_tokens`
- `reasoning_output_tokens`
- `total_tokens`
- `token_events`
- `task_count`
- `tool_calls`

### 3. `codex_tool_df`

Purpose:

- Codex-specific tool usage charts

One row per tool call event or one aggregated row per session/tool pair.

Required columns:

- `session_id`
- `tool_name`
- `count`
- `cwd`

## Tool Usage Extraction

Tool usage for Codex must be independent from Augment.

Source of truth:

- `response_item` events where `payload.type == "function_call"`

Possible supplemental signals:

- `function_call_output`

Recommended counting rule for v1:

- count each `function_call` as one tool invocation
- use `payload.name` as `tool_name`
- aggregate per session and per tool

Do not try to map tool calls to token deltas in v1 unless needed for a specific chart.

## Session Boundaries and Timestamps

Do not infer session timing from the directory path alone.

Use:

- start time: `session_meta.payload.timestamp` when available
- fallback start time: first event timestamp
- end time: last event timestamp or last accepted token snapshot timestamp

Reason:

- observed Codex sessions can span beyond the day folder they are stored under

## UX Scope for V1

To avoid breaking existing behavior:

- keep current `My Usage` as Augment-only
- keep current `Team Usage` unchanged
- add one new tab: `Codex Usage`

Why:

- Augment charts assume a specific row schema and pricing model
- Codex has different token semantics and different metadata richness
- additive isolation is safer than trying to merge sources into the existing callbacks

## Codex V1 Metrics

Recommended summary cards:

- Sessions
- Input Tokens
- Output Tokens
- Cached Input Tokens
- Reasoning Tokens
- Tool Calls

Recommended charts:

- token deltas over time
- cumulative active tokens over time
- cached vs non-cached input over time
- reasoning output over time
- tool calls by tool name
- sessions by workspace `cwd`
- session duration distribution

Recommended tables:

- session summary table
- tool usage by session

## Non-Goals for V1

These should not be added in the first Codex pass:

- changing current Augment callbacks
- merging Codex into current export/import format
- estimating Codex cost without a reliable model identifier and pricing source
- forcing a model breakdown chart when only `model_provider` is reliably visible

## Configuration

Add a new configuration input:

- `CODEX_SESSIONS_DIR`

Default:

- `~/.codex/sessions`

Do not reuse:

- `AUGMENT_SESSIONS_DIR`

## Implementation Plan

### Phase 1: Loader

Add new functions in [data_loader.py](/Users/plambert/Documents/Work/augmentUsage/data_loader.py):

- `load_codex_usage()`
- `load_codex_sessions()`
- `extract_codex_tool_usage()`

Keep them separate from:

- `load_sessions()`
- `extract_tool_usage()`

### Phase 2: App Wiring

In [app.py](/Users/plambert/Documents/Work/augmentUsage/app.py):

- add a Codex load path alongside `_load_and_prepare()`
- do not rename or overload existing `df`
- introduce separate globals such as:
  - `codex_df`
  - `codex_sessions_df`
  - `codex_tool_df`

### Phase 3: UI

Add a new tab:

- `Codex Usage`

Create new callbacks scoped only to Codex components.

Do not extend the existing large Augment callback in place unless required.

### Phase 4: Docs

Update [README.md](/Users/plambert/Documents/Work/augmentUsage/README.md) after implementation:

- explain the second data source
- document `CODEX_SESSIONS_DIR`
- clarify that Augment and Codex are displayed in separate views in v1

## Validation Requirements

The implementation must include checks proving Codex aggregation is safe.

### Session-Level Validation

For each Codex session:

- sum of derived delta `input_tokens` must equal final accepted cumulative `input_tokens`
- sum of derived delta `cached_input_tokens` must equal final accepted cumulative `cached_input_tokens`
- sum of derived delta `output_tokens` must equal final accepted cumulative `output_tokens`
- sum of derived delta `reasoning_output_tokens` must equal final accepted cumulative `reasoning_output_tokens`
- sum of derived delta `total_tokens` must equal final accepted cumulative `total_tokens`

### Structural Validation

- cumulative totals must never decrease within a session
- duplicate cumulative snapshots must not create extra delta rows
- sessions without token data must not crash the dashboard
- sessions with `turn_aborted` must still produce valid partial usage

## Test Cases

Minimum test coverage:

1. Single-session file with unique cumulative token snapshots
2. Session file with duplicate `token_count` snapshots
3. Session file with null `payload.info` on the first `token_count`
4. Session file with tool calls but no token_count
5. Session file spanning multiple tasks
6. Session file with `turn_aborted`

## Open Questions

These should be answered before any V2 merge view:

- Is there a reliable Codex model identifier available elsewhere in logs?
- Should `reasoning_output_tokens` be shown as a separate card only, or also included in advanced tables?
- Should a future combined view compare only common fields:
  - `input_tokens`
  - `output_tokens`
  - cached input
  and leave source-specific fields separate?

## Decision Summary

The key implementation decision is:

- Codex aggregation must be based on deduplicated cumulative `total_token_usage` snapshots, not on raw `last_token_usage`

That is the only approach that preserves the same additive accounting model used today for Augment.
