from dash import Dash, html, dcc, Input, Output
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from data_loader import load_sessions

# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
df = load_sessions()

# Ensure numeric columns are numeric
TOKEN_COLS = [
    "input_tokens", "output_tokens", "cache_read_input_tokens",
    "cache_creation_input_tokens", "system_prompt_tokens", "chat_history_tokens",
    "current_message_tokens", "max_context_tokens", "tool_definitions_tokens",
    "tool_result_tokens", "assistant_response_tokens",
]
for col in TOKEN_COLS:
    df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

df = df.sort_values("finished_at").reset_index(drop=True)

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
        html.P(
            f"{len(df)} exchanges across {df['session_id'].nunique()} sessions",
            style={"textAlign": "center", "color": "#888", "marginBottom": "20px"},
        ),
        # Date range picker
        html.Div(
            style={"display": "flex", "justifyContent": "center", "marginBottom": "20px"},
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
            ],
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
        # Charts row 3
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


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------
@app.callback(
    [
        Output("card-sessions", "children"),
        Output("card-exchanges", "children"),
        Output("card-input", "children"),
        Output("card-output", "children"),
        Output("card-cache", "children"),
        Output("token-time", "figure"),
        Output("token-breakdown", "figure"),
        Output("session-bar", "figure"),
        Output("model-pie", "figure"),
        Output("cache-efficiency", "figure"),
    ],
    [Input("date-range", "start_date"), Input("date-range", "end_date")],
)
def update_dashboard(start_date, end_date):
    dff = _filter(start_date, end_date)

    # --- Summary cards ---
    n_sessions = dff["session_id"].nunique()
    n_exchanges = len(dff)
    total_input = int(dff["input_tokens"].sum())
    total_output = int(dff["output_tokens"].sum())
    total_cache = int(dff["cache_read_input_tokens"].sum())

    # --- 1. Token usage over time ---
    fig_time = go.Figure()
    for col, name, color in [
        ("input_tokens", "Input", "#636EFA"),
        ("output_tokens", "Output", "#EF553B"),
        ("cache_read_input_tokens", "Cache Read", "#00CC96"),
    ]:
        fig_time.add_trace(go.Scatter(
            x=dff["finished_at"], y=dff[col], mode="lines", name=name,
            line=dict(color=color, width=1.5),
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
    fig_breakdown = go.Figure(go.Bar(
        x=list(breakdown_sums.values()),
        y=list(breakdown_sums.keys()),
        orientation="h",
        marker_color=px.colors.qualitative.Plotly[:len(breakdown_cols)],
    ))
    fig_breakdown.update_layout(
        template=PLOT_TEMPLATE, title="Token Breakdown by Type",
        xaxis_title="Total Tokens", yaxis_title="",
        paper_bgcolor="#1e1e2f", plot_bgcolor="#1e1e2f",
        margin=dict(l=140, r=20, t=40, b=40),
    )

    # --- 3. Per-session summary (top 20) ---
    session_totals = (
        dff.groupby("session_id")[["input_tokens", "output_tokens"]]
        .sum()
        .assign(total=lambda x: x["input_tokens"] + x["output_tokens"])
        .nlargest(20, "total")
        .sort_values("total")
    )
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
    fig_session.update_layout(
        template=PLOT_TEMPLATE, title="Top 20 Sessions by Total Tokens",
        barmode="stack", xaxis_title="Tokens", yaxis_title="Session",
        paper_bgcolor="#1e1e2f", plot_bgcolor="#1e1e2f",
        margin=dict(l=110, r=20, t=40, b=40), legend=dict(orientation="h", y=-0.15),
    )

    # --- 4. Model usage (donut) ---
    model_totals = (
        dff.groupby("model_id")[["input_tokens", "output_tokens"]]
        .sum()
        .assign(total=lambda x: x["input_tokens"] + x["output_tokens"])
        .sort_values("total", ascending=False)
    )
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

    # --- 5. Cache efficiency ---
    fig_cache = go.Figure()
    fig_cache.add_trace(go.Scatter(
        x=dff["finished_at"], y=dff["cache_read_input_tokens"],
        mode="lines", name="Cache Read", line=dict(color="#00CC96", width=1.5),
    ))
    fig_cache.add_trace(go.Scatter(
        x=dff["finished_at"], y=dff["cache_creation_input_tokens"],
        mode="lines", name="Cache Creation", line=dict(color="#FFA15A", width=1.5),
    ))
    fig_cache.update_layout(
        template=PLOT_TEMPLATE, title="Cache Efficiency Over Time",
        xaxis_title="Time", yaxis_title="Tokens",
        paper_bgcolor="#1e1e2f", plot_bgcolor="#1e1e2f",
        margin=dict(l=50, r=20, t=40, b=40), legend=dict(orientation="h", y=-0.15),
    )

    return (
        _fmt(n_sessions), _fmt(n_exchanges),
        _fmt(total_input), _fmt(total_output), _fmt(total_cache),
        fig_time, fig_breakdown, fig_session, fig_model, fig_cache,
    )


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app.run(port=8050, debug=False)