"""Load Augment session data from ~/.augment/sessions/ into a pandas DataFrame."""

import json
import os
import warnings
from pathlib import Path

import pandas as pd
import requests

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


# ---------------------------------------------------------------------------
# Model ID mapping: session model_id -> llm-prices id
# ---------------------------------------------------------------------------
MODEL_ID_MAP = {
    "claude-haiku-4-5": "claude-4.5-haiku",
    "claude-sonnet-4-6": "claude-sonnet-4.5",
    "claude-opus-4-6": "claude-opus-4-5",
}

# Fallback prices (per million tokens) if API is unreachable
FALLBACK_PRICES: dict[str, dict[str, float]] = {
    "claude-4.5-haiku": {"input": 1.0, "input_cached": 0.1, "output": 5.0},
    "claude-sonnet-4.5": {"input": 3.0, "input_cached": 0.3, "output": 15.0},
    "claude-opus-4-5": {"input": 5.0, "input_cached": 0.5, "output": 25.0},
}

LLM_PRICES_URL = "https://www.llm-prices.com/current-v1.json"


def fetch_pricing() -> dict[str, dict[str, float]]:
    """Fetch pricing data from llm-prices API.

    Returns a dict mapping llm-prices model id -> {input, input_cached, output}
    prices in USD per million tokens.
    """
    try:
        resp = requests.get(LLM_PRICES_URL, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        warnings.warn(f"Could not fetch pricing from {LLM_PRICES_URL}: {exc}. Using fallback prices.")
        return FALLBACK_PRICES.copy()

    prices: dict[str, dict[str, float]] = {}
    needed_ids = set(MODEL_ID_MAP.values())

    entries = data.get("prices", data) if isinstance(data, dict) else data
    for entry in entries:
        model_id = entry.get("id", "")
        if model_id not in needed_ids:
            continue
        price_info: dict[str, float] = {}
        price_info["input"] = float(entry.get("input", 0))
        price_info["output"] = float(entry.get("output", 0))
        # Use input_cached if available, otherwise fall back to input price
        if "input_cached" in entry and entry["input_cached"] is not None:
            price_info["input_cached"] = float(entry["input_cached"])
        else:
            price_info["input_cached"] = price_info["input"]
        prices[model_id] = price_info

    # Fill in any missing models from fallback
    for model_id in needed_ids:
        if model_id not in prices:
            if model_id in FALLBACK_PRICES:
                prices[model_id] = FALLBACK_PRICES[model_id]

    return prices


def get_username() -> str:
    """Auto-detect the current username from the home directory path."""
    return Path.home().name


def compute_cost(row: pd.Series, pricing: dict[str, dict[str, float]]) -> float:
    """Compute estimated cost in USD for a single exchange row."""
    llm_id = MODEL_ID_MAP.get(row.get("model_id", ""), "")
    if not llm_id or llm_id not in pricing:
        return 0.0

    p = pricing[llm_id]
    input_price = p.get("input", 0)
    output_price = p.get("output", 0)

    cost = (
        (row.get("input_tokens", 0) or 0) * input_price / 1_000_000
        + (row.get("output_tokens", 0) or 0) * output_price / 1_000_000
        + (row.get("cache_creation_input_tokens", 0) or 0) * input_price / 1_000_000
    )
    return cost

