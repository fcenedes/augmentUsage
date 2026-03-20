"""Load Augment session data from ~/.augment/sessions/ into a pandas DataFrame."""

import json
import os
import warnings
from pathlib import Path

import pandas as pd

TOKEN_FIELDS = [
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


def load_sessions(sessions_dir: str | None = None) -> pd.DataFrame:
    """Read all JSON session files and return a DataFrame with one row per token_usage entry.

    Parameters
    ----------
    sessions_dir : str or None
        Path to the sessions directory. Defaults to ``~/.augment/sessions/``.

    Returns
    -------
    pd.DataFrame
        Columns: session_id, model_id, created, exchange_idx, finished_at,
        plus all TOKEN_FIELDS.
    """
    if sessions_dir is None:
        sessions_dir = os.path.expanduser("~/.augment/sessions")

    sessions_path = Path(sessions_dir)
    if not sessions_path.is_dir():
        warnings.warn(f"Sessions directory not found: {sessions_path}")
        return _empty_dataframe()

    rows: list[dict] = []
    for filepath in sorted(sessions_path.glob("*.json")):
        try:
            with open(filepath, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            warnings.warn(f"Skipping malformed file {filepath.name}: {exc}")
            continue

        session_id = data.get("sessionId", filepath.stem)
        model_id = (data.get("agentState") or {}).get("modelId")
        created = data.get("created")

        for exchange_idx, chat_item in enumerate(data.get("chatHistory") or []):
            finished_at = chat_item.get("finishedAt")
            exchange = chat_item.get("exchange") or {}
            for node in exchange.get("response_nodes") or []:
                token_usage = node.get("token_usage")
                if not token_usage:
                    continue
                row = {
                    "session_id": session_id,
                    "model_id": model_id,
                    "created": created,
                    "exchange_idx": exchange_idx,
                    "finished_at": finished_at,
                }
                for field in TOKEN_FIELDS:
                    row[field] = token_usage.get(field)
                rows.append(row)

    if not rows:
        return _empty_dataframe()

    df = pd.DataFrame(rows)
    # Parse timestamps
    df["created"] = pd.to_datetime(df["created"], errors="coerce", utc=True)
    df["finished_at"] = pd.to_datetime(df["finished_at"], errors="coerce", utc=True)
    return df


def _empty_dataframe() -> pd.DataFrame:
    """Return an empty DataFrame with the expected schema."""
    cols = ["session_id", "model_id", "created", "exchange_idx", "finished_at"] + TOKEN_FIELDS
    return pd.DataFrame(columns=cols)

