from dash import Dash, html, dcc, Input, Output, State, callback_context
import plotly.express as px
import plotly.graph_objects as go
import numpy as np
import pandas as pd
from data_loader import load_sessions, fetch_pricing, compute_cost, MODEL_ID_MAP

# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
TOKEN_COLS = [
    "input_tokens", "output_tokens", "cache_read_input_tokens",
    "cache_creation_input_tokens", "system_prompt_tokens", "chat_history_tokens",
    "current_message_tokens", "max_context_tokens", "tool_definitions_tokens",
    "tool_result_tokens", "assistant_response_tokens",
]


def _load_and_prepare() -> tuple[pd.DataFrame, dict]:
    """Load sessions, clean numeric columns, compute costs, return (df, pricing)."""
    df = load_sessions()
    pricing = fetch_pricing()
    for col in TOKEN_COLS:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
    df = df.sort_values("finished_at").reset_index(drop=True)
    # Compute per-exchange cost
    df["cost_usd"] = df.apply(lambda r: compute_cost(r, pricing), axis=1)
    return df, pricing


df, pricing = _load_and_prepare()

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = Dash(__name__)

CARD_STYLE = {
    "backgroundColor": "#1e1e2f",
    "borderRadius": "10px",
    "padding": "20px",
    "textAlign": "center",
    "flex": "1",
    "minWidth": "160px",
}
CARD_TITLE = {"color": "#aaa", "fontSize": "0.85rem", "marginBottom": "6px"}
CARD_VALUE = {"color": "#fff", "fontSize": "1.6rem", "fontWeight": "bold"}
PLOT_TEMPLATE = "plotly_dark"


def _fmt(n: int) -> str:
    """Format large numbers with K/M suffix."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def make_card(title: str, value_id: str):
    return html.Div(
        [
            html.Div(title, style=CARD_TITLE),
            html.Div(id=value_id, style=CARD_VALUE),
        ],
        style=CARD_STYLE,
    )


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------
app.layout = html.Div(
    style={
        "backgroundColor": "#121220",
        "color": "#e0e0e0",
        "fontFamily": "'Segoe UI', Roboto, sans-serif",
        "minHeight": "100vh",
        "padding": "24px",
    },
    children=[
        html.H1(
            "Augment Session Dashboard",
            style={"textAlign": "center", "marginBottom": "4px", "color": "#fff"},
        ),

        # Hidden store for refresh trigger
        dcc.Store(id="refresh-trigger", data=0),
        # Date range picker + refresh button
        html.Div(
            style={"display": "flex", "justifyContent": "center", "alignItems": "center", "marginBottom": "20px", "gap": "12px"},
            children=[
                html.Label("Date range: ", style={"marginRight": "8px", "paddingTop": "6px"}),
                dcc.DatePickerRange(
                    id="date-range",
                    min_date_allowed=df["finished_at"].min() if not df.empty else None,
                    max_date_allowed=df["finished_at"].max() if not df.empty else None,
                    start_date=df["finished_at"].min() if not df.empty else None,
                    end_date=df["finished_at"].max() if not df.empty else None,
                    style={"backgroundColor": "#1e1e2f"},
                ),
                html.Button(
                    "🔄 Refresh Data",
                    id="refresh-btn",
                    n_clicks=0,
                    style={
                        "backgroundColor": "#3a3a5c",
                        "color": "#fff",
                        "border": "1px solid #555",
                        "borderRadius": "6px",
                        "padding": "8px 16px",
                        "cursor": "pointer",
                        "fontSize": "0.9rem",
                    },
                ),
            ],
        ),
        # Subtitle (updated on refresh)
        html.P(
            id="subtitle",
            style={"textAlign": "center", "color": "#888", "marginBottom": "20px"},
        ),
        # Summary cards
        html.Div(
            id="summary-cards",
            style={"display": "flex", "gap": "16px", "flexWrap": "wrap", "marginBottom": "24px"},
            children=[
                make_card("Total Sessions", "card-sessions"),
                make_card("Total Exchanges", "card-exchanges"),
                make_card("Input Tokens", "card-input"),
                make_card("Output Tokens", "card-output"),
                make_card("Cache Read Tokens", "card-cache"),
                make_card("Estimated Cost", "card-cost"),
            ],
        ),
        # Charts row 1
        html.Div(
            style={"display": "flex", "gap": "16px", "flexWrap": "wrap", "marginBottom": "24px"},
            children=[
                html.Div(dcc.Graph(id="token-time"), style={"flex": "1", "minWidth": "400px"}),
                html.Div(dcc.Graph(id="token-breakdown"), style={"flex": "1", "minWidth": "400px"}),
            ],
        ),
        # Charts row 2
        html.Div(
            style={"display": "flex", "gap": "16px", "flexWrap": "wrap", "marginBottom": "24px"},
            children=[
                html.Div(dcc.Graph(id="session-bar"), style={"flex": "1", "minWidth": "400px"}),
                html.Div(dcc.Graph(id="model-pie"), style={"flex": "1", "minWidth": "400px"}),
            ],
        ),
        # Charts row 3 – Cost charts
        html.Div(
            style={"display": "flex", "gap": "16px", "flexWrap": "wrap", "marginBottom": "24px"},
            children=[
                html.Div(dcc.Graph(id="cost-time"), style={"flex": "1", "minWidth": "400px"}),
                html.Div(dcc.Graph(id="cost-model"), style={"flex": "1", "minWidth": "400px"}),
            ],
        ),
        # Charts row 4
        html.Div(
            style={"display": "flex", "justifyContent": "center", "marginBottom": "24px"},
            children=[
                html.Div(dcc.Graph(id="cache-efficiency"), style={"flex": "1", "maxWidth": "900px"}),
            ],
        ),
    ],
)


# ---------------------------------------------------------------------------
# Helper: filter by date range
# ---------------------------------------------------------------------------
def _filter(start, end):
    dff = df.copy()
    if start:
        dff = dff[dff["finished_at"] >= pd.Timestamp(start, tz="UTC")]
    if end:
        dff = dff[dff["finished_at"] <= pd.Timestamp(end, tz="UTC") + pd.Timedelta(days=1)]
    return dff


def _fmt_cost(v: float) -> str:
    """Format a USD cost value."""
    if v >= 1000:
        return f"${v:,.0f}"
    if v >= 1:
        return f"${v:.2f}"
    return f"${v:.4f}"


# ---------------------------------------------------------------------------
# Callback: Refresh data
# ---------------------------------------------------------------------------
@app.callback(
    [
        Output("refresh-trigger", "data"),
        Output("date-range", "min_date_allowed"),
        Output("date-range", "max_date_allowed"),
        Output("date-range", "start_date"),
        Output("date-range", "end_date"),
    ],
    Input("refresh-btn", "n_clicks"),
    prevent_initial_call=True,
)
def refresh_data(n_clicks):
    global df, pricing
    df, pricing = _load_and_prepare()
    min_date = df["finished_at"].min() if not df.empty else None
    max_date = df["finished_at"].max() if not df.empty else None
    return n_clicks, min_date, max_date, min_date, max_date


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------
@app.callback(
    [
        Output("subtitle", "children"),
        Output("card-sessions", "children"),
        Output("card-exchanges", "children"),
        Output("card-input", "children"),
        Output("card-output", "children"),
        Output("card-cache", "children"),
        Output("card-cost", "children"),
        Output("token-time", "figure"),
        Output("token-breakdown", "figure"),
        Output("session-bar", "figure"),
        Output("model-pie", "figure"),
        Output("cost-time", "figure"),
        Output("cost-model", "figure"),
        Output("cache-efficiency", "figure"),
    ],
    [
        Input("date-range", "start_date"),
        Input("date-range", "end_date"),
        Input("refresh-trigger", "data"),
    ],
)
def update_dashboard(start_date, end_date, _refresh):
    dff = _filter(start_date, end_date)

    # --- Subtitle ---
    subtitle = f"{len(dff)} exchanges across {dff['session_id'].nunique()} sessions"

    # --- Summary cards ---
    n_sessions = dff["session_id"].nunique()
    n_exchanges = len(dff)
    total_input = int(dff["input_tokens"].sum())
    total_output = int(dff["output_tokens"].sum())
    total_cache = int(dff["cache_read_input_tokens"].sum())
    total_cost = dff["cost_usd"].sum()

    # --- Prepare line-chart dataframe with gaps between sessions ---
    dff_plot = dff.sort_values("finished_at").copy()
    if len(dff_plot) > 1:
        time_diff = dff_plot["finished_at"].diff()
        gap_mask = time_diff > pd.Timedelta(minutes=5)
        gap_indices = dff_plot.index[gap_mask]
        gap_rows = []
        for idx in gap_indices:
            gap_row = dff_plot.loc[idx].copy()
            for col in TOKEN_COLS + ["cost_usd"]:
                gap_row[col] = float("nan")
            gap_row["finished_at"] = dff_plot.loc[idx, "finished_at"] - pd.Timedelta(seconds=1)
            gap_rows.append(gap_row)
        if gap_rows:
            dff_plot = pd.concat([dff_plot, pd.DataFrame(gap_rows)]).sort_values("finished_at")

    # --- 1. Token usage over time (replace 0 with NaN so Plotly skips them) ---
    fig_time = go.Figure()
    for col, name, color in [
        ("input_tokens", "Input", "#636EFA"),
        ("output_tokens", "Output", "#EF553B"),
        ("cache_read_input_tokens", "Cache Read", "#00CC96"),
    ]:
        y_vals = dff_plot[col].replace(0, np.nan)
        fig_time.add_trace(go.Scatter(
            x=dff_plot["finished_at"], y=y_vals, mode="lines", name=name,
            line=dict(color=color, width=1.5), connectgaps=False,
        ))
    fig_time.update_layout(
        template=PLOT_TEMPLATE, title="Token Usage Over Time",
        xaxis_title="Time", yaxis_title="Tokens",
        paper_bgcolor="#1e1e2f", plot_bgcolor="#1e1e2f",
        margin=dict(l=50, r=20, t=40, b=40), legend=dict(orientation="h", y=-0.15),
    )

    # --- 2. Token breakdown (stacked bar) ---
    breakdown_cols = [
        "system_prompt_tokens", "chat_history_tokens", "tool_definitions_tokens",
        "tool_result_tokens", "current_message_tokens", "assistant_response_tokens",
    ]
    breakdown_sums = {c.replace("_tokens", "").replace("_", " ").title(): int(dff[c].sum()) for c in breakdown_cols}
    # Filter out zero-total breakdown categories
    filtered_labels = [k for k, v in breakdown_sums.items() if v > 0]
    filtered_values = [breakdown_sums[k] for k in filtered_labels]
    filtered_colors = [px.colors.qualitative.Plotly[i] for i, c in enumerate(breakdown_cols)
                       if breakdown_sums[c.replace("_tokens", "").replace("_", " ").title()] > 0]
    fig_breakdown = go.Figure(go.Bar(
        x=filtered_values,
        y=filtered_labels,
        orientation="h",
        marker_color=filtered_colors if filtered_colors else px.colors.qualitative.Plotly[:1],
    ))
    fig_breakdown.update_layout(
        template=PLOT_TEMPLATE, title="Token Breakdown by Type",
        xaxis_title="Total Tokens", yaxis_title="",
        paper_bgcolor="#1e1e2f", plot_bgcolor="#1e1e2f",
        margin=dict(l=140, r=20, t=40, b=40),
    )

    # --- 3. Per-session summary (top 20) with cost ---
    session_totals = (
        dff.groupby("session_id")[["input_tokens", "output_tokens", "cost_usd"]]
        .sum()
        .assign(total=lambda x: x["input_tokens"] + x["output_tokens"])
    )
    # Filter out sessions with zero total tokens
    session_totals = session_totals[session_totals["total"] > 0]
    session_totals = session_totals.nlargest(20, "total").sort_values("total")
    fig_session = go.Figure()
    fig_session.add_trace(go.Bar(
        y=session_totals.index.astype(str).str[:12],
        x=session_totals["input_tokens"], name="Input",
        orientation="h", marker_color="#636EFA",
    ))
    fig_session.add_trace(go.Bar(
        y=session_totals.index.astype(str).str[:12],
        x=session_totals["output_tokens"], name="Output",
        orientation="h", marker_color="#EF553B",
    ))
    # Add cost as text annotation
    fig_session.update_layout(
        template=PLOT_TEMPLATE, title="Top 20 Sessions by Total Tokens",
        barmode="stack", xaxis_title="Tokens", yaxis_title="Session",
        paper_bgcolor="#1e1e2f", plot_bgcolor="#1e1e2f",
        margin=dict(l=110, r=80, t=40, b=40), legend=dict(orientation="h", y=-0.15),
    )
    # Add cost annotations on the right side of bars
    for i, (sid, row) in enumerate(session_totals.iterrows()):
        fig_session.add_annotation(
            x=row["total"], y=str(sid)[:12],
            text=f" {_fmt_cost(row['cost_usd'])}",
            showarrow=False, xanchor="left",
            font=dict(color="#00CC96", size=10),
        )

    # --- 4. Model usage (donut) ---
    model_totals = (
        dff.groupby("model_id")[["input_tokens", "output_tokens"]]
        .sum()
        .assign(total=lambda x: x["input_tokens"] + x["output_tokens"])
        .sort_values("total", ascending=False)
    )
    # Filter out models with zero total tokens
    model_totals = model_totals[model_totals["total"] > 0]
    fig_model = go.Figure(go.Pie(
        labels=model_totals.index,
        values=model_totals["total"],
        hole=0.45,
        textinfo="label+percent",
        marker=dict(colors=px.colors.qualitative.Plotly),
    ))
    fig_model.update_layout(
        template=PLOT_TEMPLATE, title="Token Consumption by Model",
        paper_bgcolor="#1e1e2f", plot_bgcolor="#1e1e2f",
        margin=dict(l=20, r=20, t=40, b=40),
    )

    # --- 5. Cost over time (cumulative line) ---
    fig_cost_time = go.Figure()
    if not dff.empty:
        dff_sorted = dff.sort_values("finished_at")
        cumulative_cost = dff_sorted["cost_usd"].cumsum()
        fig_cost_time.add_trace(go.Scatter(
            x=dff_sorted["finished_at"], y=cumulative_cost,
            mode="lines", name="Cumulative Cost",
            line=dict(color="#AB63FA", width=2),
            fill="tozeroy", fillcolor="rgba(171,99,250,0.15)",
        ))
    fig_cost_time.update_layout(
        template=PLOT_TEMPLATE, title="Cumulative Estimated Cost Over Time",
        xaxis_title="Time", yaxis_title="Cost (USD)",
        paper_bgcolor="#1e1e2f", plot_bgcolor="#1e1e2f",
        margin=dict(l=60, r=20, t=40, b=40),
    )

    # --- 6. Cost by model (bar) ---
    model_costs = dff.groupby("model_id")["cost_usd"].sum().sort_values(ascending=True)
    # Filter out models with zero cost
    model_costs = model_costs[model_costs > 0]
    fig_cost_model = go.Figure(go.Bar(
        y=model_costs.index,
        x=model_costs.values,
        orientation="h",
        marker_color="#AB63FA",
        text=[_fmt_cost(v) for v in model_costs.values],
        textposition="auto",
    ))
    fig_cost_model.update_layout(
        template=PLOT_TEMPLATE, title="Estimated Cost by Model",
        xaxis_title="Cost (USD)", yaxis_title="",
        paper_bgcolor="#1e1e2f", plot_bgcolor="#1e1e2f",
        margin=dict(l=140, r=20, t=40, b=40),
    )

    # --- 7. Cache efficiency (replace 0 with NaN) ---
    fig_cache = go.Figure()
    cache_read_vals = dff_plot["cache_read_input_tokens"].replace(0, np.nan)
    cache_create_vals = dff_plot["cache_creation_input_tokens"].replace(0, np.nan)
    fig_cache.add_trace(go.Scatter(
        x=dff_plot["finished_at"], y=cache_read_vals,
        mode="lines", name="Cache Read", line=dict(color="#00CC96", width=1.5),
        connectgaps=False,
    ))
    fig_cache.add_trace(go.Scatter(
        x=dff_plot["finished_at"], y=cache_create_vals,
        mode="lines", name="Cache Creation", line=dict(color="#FFA15A", width=1.5),
        connectgaps=False,
    ))
    fig_cache.update_layout(
        template=PLOT_TEMPLATE, title="Cache Efficiency Over Time",
        xaxis_title="Time", yaxis_title="Tokens",
        paper_bgcolor="#1e1e2f", plot_bgcolor="#1e1e2f",
        margin=dict(l=50, r=20, t=40, b=40), legend=dict(orientation="h", y=-0.15),
    )

    return (
        subtitle,
        _fmt(n_sessions), _fmt(n_exchanges),
        _fmt(total_input), _fmt(total_output), _fmt(total_cache),
        _fmt_cost(total_cost),
        fig_time, fig_breakdown, fig_session, fig_model,
        fig_cost_time, fig_cost_model, fig_cache,
    )


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app.run(port=8050, debug=False)