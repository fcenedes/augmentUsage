import os

from dash import Dash, html, dcc, Input, Output, State, callback_context, no_update, dash_table
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
import numpy as np
import pandas as pd
import json
import base64
from datetime import datetime, timedelta
from data_loader import load_sessions, fetch_pricing, compute_cost, MODEL_ID_MAP, get_username, extract_tool_usage

# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
TOKEN_COLS = [
    "input_tokens", "output_tokens", "cache_read_input_tokens",
    "cache_creation_input_tokens", "system_prompt_tokens", "chat_history_tokens",
    "current_message_tokens", "max_context_tokens", "tool_definitions_tokens",
    "tool_result_tokens", "assistant_response_tokens",
]


def _load_and_prepare() -> tuple[pd.DataFrame, dict, pd.DataFrame]:
    """Load sessions, clean numeric columns, compute costs, return (df, pricing, tool_df)."""
    df = load_sessions()
    pricing = fetch_pricing()
    tool_df = extract_tool_usage()
    for col in TOKEN_COLS:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
    df = df.sort_values("finished_at").reset_index(drop=True)
    # Compute per-exchange cost
    df["cost_usd"] = df.apply(lambda r: compute_cost(r, pricing), axis=1)
    return df, pricing, tool_df


df, pricing, tool_df = _load_and_prepare()

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = Dash(
    __name__,
    external_stylesheets=[
        "https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;500;600;700&family=Space+Mono:wght@400;700&display=swap"
    ],
    suppress_callback_exceptions=True,
)

USERNAME = get_username()

# ---------------------------------------------------------------------------
# Redis Brand Dark Mode Palette
# ---------------------------------------------------------------------------
REDIS_BG = "#0A1A23"
REDIS_CARD_BG = "#122A35"
REDIS_SECTION_BG = "#1C3A47"
REDIS_TEXT = "#F0F4F5"
REDIS_TEXT_SECONDARY = "#C8D1D5"
REDIS_TEXT_MUTED = "#5A6A72"
REDIS_RED = "#FF4438"
REDIS_RED_HOVER = "#FF7566"
REDIS_BORDER = "#2D4754"
REDIS_BORDER_LIGHT = "#3D5764"
REDIS_COLORWAY = ["#FF4438", "#8AB4C7", "#FF7566", "#C8D1D5", "#5A6A72", "#2D4754"]
REDIS_FONT = "'Space Grotesk', sans-serif"
REDIS_MONO = "'Space Mono', monospace"

# Custom Plotly template
REDIS_DARK_TEMPLATE = go.layout.Template(
    layout=go.Layout(
        paper_bgcolor=REDIS_CARD_BG,
        plot_bgcolor=REDIS_CARD_BG,
        font=dict(family=REDIS_FONT, color=REDIS_TEXT),
        colorway=REDIS_COLORWAY,
        xaxis=dict(gridcolor=REDIS_SECTION_BG, zerolinecolor=REDIS_SECTION_BG),
        yaxis=dict(gridcolor=REDIS_SECTION_BG, zerolinecolor=REDIS_SECTION_BG),
    )
)
pio.templates["redis_dark"] = REDIS_DARK_TEMPLATE
PLOT_TEMPLATE = "redis_dark"

# ---------------------------------------------------------------------------
# Redis Brand Light Mode Palette
# ---------------------------------------------------------------------------
LIGHT_BG = "#FFFFFF"
LIGHT_CARD_BG = "#FFFFFF"
LIGHT_SECTION_BG = "#F0F4F5"
LIGHT_TEXT = "#091A23"
LIGHT_TEXT_SECONDARY = "#163341"
LIGHT_TEXT_MUTED = "#8A99A0"
LIGHT_BORDER = "#163341"
LIGHT_BORDER_LIGHT = "#2D4754"

REDIS_LIGHT_TEMPLATE = go.layout.Template(
    layout=go.Layout(
        paper_bgcolor=LIGHT_CARD_BG,
        plot_bgcolor=LIGHT_CARD_BG,
        font=dict(family=REDIS_FONT, color=LIGHT_TEXT),
        colorway=REDIS_COLORWAY,
        xaxis=dict(gridcolor=LIGHT_SECTION_BG, zerolinecolor=LIGHT_SECTION_BG),
        yaxis=dict(gridcolor=LIGHT_SECTION_BG, zerolinecolor=LIGHT_SECTION_BG),
    )
)
pio.templates["redis_light"] = REDIS_LIGHT_TEMPLATE


def _theme_vals(theme: str) -> dict:
    """Return a dict of palette values for the given theme."""
    if theme == "light":
        return dict(
            bg=LIGHT_BG, card_bg=LIGHT_CARD_BG, section_bg=LIGHT_SECTION_BG,
            text=LIGHT_TEXT, text_secondary=LIGHT_TEXT_SECONDARY, text_muted=LIGHT_TEXT_MUTED,
            red=REDIS_RED, red_hover=REDIS_RED_HOVER,
            border=LIGHT_BORDER, border_light=LIGHT_BORDER_LIGHT,
            template="redis_light",
        )
    return dict(
        bg=REDIS_BG, card_bg=REDIS_CARD_BG, section_bg=REDIS_SECTION_BG,
        text=REDIS_TEXT, text_secondary=REDIS_TEXT_SECONDARY, text_muted=REDIS_TEXT_MUTED,
        red=REDIS_RED, red_hover=REDIS_RED_HOVER,
        border=REDIS_BORDER, border_light=REDIS_BORDER_LIGHT,
        template="redis_dark",
    )


CARD_STYLE = {
    "backgroundColor": REDIS_CARD_BG,
    "borderRadius": "5px",
    "padding": "20px",
    "textAlign": "center",
    "flex": "1",
    "minWidth": "160px",
    "border": f"1px solid {REDIS_BORDER}",
}
CARD_TITLE = {"color": REDIS_TEXT_SECONDARY, "fontSize": "0.85rem", "marginBottom": "8px", "fontFamily": REDIS_FONT}
CARD_VALUE = {"color": REDIS_RED, "fontSize": "1.6rem", "fontWeight": "bold", "fontFamily": REDIS_MONO}

BTN_STYLE = {
    "backgroundColor": REDIS_RED,
    "color": "#fff",
    "border": "none",
    "borderRadius": "5px",
    "padding": "8px 16px",
    "cursor": "pointer",
    "fontSize": "0.9rem",
    "fontFamily": REDIS_FONT,
    "transition": "all 0.2s ease-in-out",
}

TAB_STYLE = {
    "backgroundColor": REDIS_CARD_BG,
    "color": REDIS_TEXT_SECONDARY,
    "border": f"1px solid {REDIS_BORDER}",
    "borderBottom": f"1px solid {REDIS_BORDER}",
    "padding": "10px 20px",
    "borderRadius": "5px 5px 0 0",
    "fontFamily": REDIS_FONT,
}

TAB_SELECTED_STYLE = {
    **TAB_STYLE,
    "backgroundColor": REDIS_SECTION_BG,
    "color": REDIS_TEXT,
    "borderBottom": f"2px solid {REDIS_RED}",
}


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
    id="main-container",
    style={
        "backgroundColor": REDIS_BG,
        "color": REDIS_TEXT,
        "fontFamily": REDIS_FONT,
        "minHeight": "100vh",
        "padding": "24px",
    },
    children=[
        # Hidden stores
        dcc.Store(id="refresh-trigger", data=0),
        dcc.Store(id="team-data-store", storage_type="session", data=[]),
        dcc.Store(id="theme-store", storage_type="local", data="dark"),
        dcc.Download(id="download-export"),
        # Auto-refresh interval (disabled by default)
        dcc.Interval(id="auto-refresh-interval", interval=60_000, disabled=True),

        # Header
        html.Div(
            style={"display": "flex", "justifyContent": "center", "alignItems": "center", "gap": "16px", "marginBottom": "4px"},
            children=[
                html.H1(
                    f"Augment Session Dashboard — {USERNAME}",
                    id="header-title",
                    style={"textAlign": "center", "marginBottom": "0", "color": REDIS_TEXT, "fontFamily": REDIS_FONT},
                ),
                html.Button(
                    "🌙", id="theme-toggle-btn", n_clicks=0,
                    style={
                        "backgroundColor": "transparent", "border": f"1px solid {REDIS_BORDER}",
                        "borderRadius": "5px", "padding": "6px 12px", "cursor": "pointer",
                        "fontSize": "1.2rem", "color": REDIS_TEXT,
                    },
                ),
            ],
        ),

        # Controls bar: date range + buttons + auto-refresh
        html.Div(
            id="controls-bar",
            style={
                "display": "flex", "justifyContent": "center", "alignItems": "center",
                "marginBottom": "20px", "gap": "12px", "flexWrap": "wrap",
                "backgroundColor": REDIS_CARD_BG, "borderRadius": "5px",
                "padding": "16px 24px", "border": f"1px solid {REDIS_BORDER}",
            },
            children=[
                html.Span("📅", style={"fontSize": "1.2rem"}),
                dcc.DatePickerRange(
                    id="date-range",
                    min_date_allowed=df["finished_at"].min() if not df.empty else None,
                    max_date_allowed=df["finished_at"].max() if not df.empty else None,
                    start_date=df["finished_at"].min() if not df.empty else None,
                    end_date=df["finished_at"].max() if not df.empty else None,
                    style={"backgroundColor": REDIS_CARD_BG},
                ),
                html.Div(style={"width": "1px", "height": "28px", "backgroundColor": REDIS_BORDER_LIGHT, "margin": "0 4px"}),
                html.Button("🔄 Refresh", id="refresh-btn", n_clicks=0, style=BTN_STYLE),
                # Auto-refresh dropdown
                html.Div(
                    style={"display": "flex", "alignItems": "center", "gap": "4px"},
                    children=[
                        html.Span("⏱️", style={"fontSize": "1rem"}),
                        dcc.Dropdown(
                            id="auto-refresh-dropdown",
                            options=[
                                {"label": "Off", "value": "off"},
                                {"label": "1 min", "value": "60"},
                                {"label": "5 min", "value": "300"},
                                {"label": "15 min", "value": "900"},
                            ],
                            value="off",
                            clearable=False,
                            style={"width": "100px", "backgroundColor": REDIS_CARD_BG, "color": REDIS_TEXT, "fontSize": "0.85rem"},
                        ),
                    ],
                ),
                html.Div(style={"width": "1px", "height": "28px", "backgroundColor": REDIS_BORDER_LIGHT, "margin": "0 4px"}),
                html.Button("📤 Export My Data", id="export-btn", n_clicks=0, style=BTN_STYLE),
                dcc.Upload(
                    id="import-upload",
                    children=html.Button("📥 Import Team Data", style=BTN_STYLE),
                    multiple=True,
                    accept=".json",
                ),
            ],
        ),

        # Import status message
        html.Div(id="import-status", style={"textAlign": "center", "color": REDIS_RED, "marginBottom": "10px"}),

        # Tabs
        dcc.Tabs(
            id="main-tabs",
            value="my-usage",
            children=[
                dcc.Tab(label="📊 My Usage", value="my-usage", style=TAB_STYLE, selected_style=TAB_SELECTED_STYLE),
                dcc.Tab(label="👥 Team Usage", value="team-usage", style=TAB_STYLE, selected_style=TAB_SELECTED_STYLE),
            ],
            style={"marginBottom": "0px"},
        ),

        # Tab content container
        html.Div(id="tab-content", style={"backgroundColor": REDIS_BG, "paddingTop": "20px"}),
    ],
)


# ---------------------------------------------------------------------------
# Tab rendering callback
# ---------------------------------------------------------------------------
@app.callback(
    Output("tab-content", "children"),
    Input("main-tabs", "value"),
)
def render_tab(tab):
    if tab == "team-usage":
        return _team_tab_layout()
    return _my_usage_layout()


def _my_usage_layout():
    """Return the 'My Usage' tab content (all existing charts)."""
    return html.Div([
        # Subtitle
        html.P(id="subtitle", style={"textAlign": "center", "color": REDIS_TEXT_MUTED, "marginBottom": "20px"}),
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
        # Charts row 2: session bar + model pie + model comparison
        html.Div(
            style={"display": "flex", "gap": "16px", "flexWrap": "wrap", "marginBottom": "24px"},
            children=[
                html.Div(dcc.Graph(id="session-bar"), style={"flex": "1", "minWidth": "400px"}),
                html.Div(dcc.Graph(id="model-pie"), style={"flex": "1", "minWidth": "400px"}),
            ],
        ),
        # Model Comparison: cost per 1K output tokens
        html.Div(
            style={"display": "flex", "gap": "16px", "flexWrap": "wrap", "marginBottom": "24px"},
            children=[
                html.Div(dcc.Graph(id="model-comparison"), style={"flex": "1", "minWidth": "400px"}),
                html.Div(dcc.Graph(id="tool-usage-chart"), style={"flex": "1", "minWidth": "400px"}),
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

        # ---- NEW ANALYTICS CHARTS ----
        html.Hr(style={"borderColor": REDIS_BORDER, "margin": "32px 0"}),
        html.H2("Advanced Analytics", style={"textAlign": "center", "color": REDIS_TEXT, "marginBottom": "24px", "fontFamily": REDIS_FONT}),

        # Chart 5: Daily/Weekly Summary
        html.Div(style={"marginBottom": "24px", "backgroundColor": REDIS_CARD_BG, "borderRadius": "5px", "padding": "16px", "border": f"1px solid {REDIS_BORDER}"}, children=[
            html.H3("Daily / Weekly Summary", style={"color": REDIS_TEXT, "marginBottom": "8px", "fontFamily": REDIS_FONT}),
            dcc.RadioItems(
                id="summary-toggle",
                options=[{"label": " Daily", "value": "daily"}, {"label": " Weekly", "value": "weekly"}],
                value="daily",
                inline=True,
                style={"marginBottom": "8px", "color": REDIS_TEXT_SECONDARY, "fontFamily": REDIS_FONT},
                inputStyle={"marginRight": "4px"},
                labelStyle={"marginRight": "16px"},
            ),
            dcc.Graph(id="daily-weekly-summary"),
        ]),

        # Chart 6: Hourly Activity Heatmap
        html.Div(style={"marginBottom": "24px", "backgroundColor": REDIS_CARD_BG, "borderRadius": "5px", "padding": "16px", "border": f"1px solid {REDIS_BORDER}"}, children=[
            html.H3("Hourly Activity Heatmap", style={"color": REDIS_TEXT, "marginBottom": "8px", "fontFamily": REDIS_FONT}),
            dcc.Graph(id="hourly-heatmap"),
        ]),

        # Charts row: Context Window + Token Efficiency
        html.Div(
            style={"display": "flex", "gap": "16px", "flexWrap": "wrap", "marginBottom": "24px"},
            children=[
                html.Div(style={"flex": "1", "minWidth": "400px", "backgroundColor": REDIS_CARD_BG, "borderRadius": "5px", "padding": "16px", "border": f"1px solid {REDIS_BORDER}"}, children=[
                    html.H3("Context Window Utilization", style={"color": REDIS_TEXT, "marginBottom": "8px", "fontFamily": REDIS_FONT}),
                    dcc.Graph(id="context-window"),
                ]),
                html.Div(style={"flex": "1", "minWidth": "400px", "backgroundColor": REDIS_CARD_BG, "borderRadius": "5px", "padding": "16px", "border": f"1px solid {REDIS_BORDER}"}, children=[
                    html.H3("Token Efficiency Ratio", style={"color": REDIS_TEXT, "marginBottom": "8px", "fontFamily": REDIS_FONT}),
                    dcc.Graph(id="token-efficiency"),
                ]),
            ],
        ),

        # Charts row: Burn Rate + Session Duration
        html.Div(
            style={"display": "flex", "gap": "16px", "flexWrap": "wrap", "marginBottom": "24px"},
            children=[
                html.Div(style={"flex": "1", "minWidth": "400px", "backgroundColor": REDIS_CARD_BG, "borderRadius": "5px", "padding": "16px", "border": f"1px solid {REDIS_BORDER}"}, children=[
                    html.H3("Daily Burn Rate + Projection", style={"color": REDIS_TEXT, "marginBottom": "8px", "fontFamily": REDIS_FONT}),
                    dcc.Graph(id="burn-rate"),
                ]),
                html.Div(style={"flex": "1", "minWidth": "400px", "backgroundColor": REDIS_CARD_BG, "borderRadius": "5px", "padding": "16px", "border": f"1px solid {REDIS_BORDER}"}, children=[
                    html.H3("Session Duration Distribution", style={"color": REDIS_TEXT, "marginBottom": "8px", "fontFamily": REDIS_FONT}),
                    dcc.Graph(id="session-duration"),
                ]),
            ],
        ),

        # ---- COST PER SESSION BREAKDOWN TABLE ----
        html.Hr(style={"borderColor": REDIS_BORDER, "margin": "32px 0"}),
        html.H2("Cost Per Session Breakdown", style={"textAlign": "center", "color": REDIS_TEXT, "marginBottom": "24px", "fontFamily": REDIS_FONT}),
        html.Div(id="cost-session-table-container", style={"marginBottom": "24px"}),

        # ---- SORTABLE DATA TABLE ----
        html.Hr(style={"borderColor": REDIS_BORDER, "margin": "32px 0"}),
        html.H2("Session Data Table", style={"textAlign": "center", "color": REDIS_TEXT, "marginBottom": "24px", "fontFamily": REDIS_FONT}),
        html.Div(id="session-data-table-container", style={"marginBottom": "24px"}),
    ])


def _team_tab_layout():
    """Return the 'Team Usage' tab content."""
    return html.Div([
        html.Div(
            id="team-summary-cards",
            style={"display": "flex", "gap": "16px", "flexWrap": "wrap", "marginBottom": "24px"},
            children=[
                make_card("Team Members", "team-card-members"),
                make_card("Total Sessions", "team-card-sessions"),
                make_card("Total Tokens", "team-card-tokens"),
                make_card("Total Cost", "team-card-cost"),
            ],
        ),
        # Team charts row 1
        html.Div(
            style={"display": "flex", "gap": "16px", "flexWrap": "wrap", "marginBottom": "24px"},
            children=[
                html.Div(dcc.Graph(id="team-cost-bar"), style={"flex": "1", "minWidth": "400px"}),
                html.Div(dcc.Graph(id="team-tokens-bar"), style={"flex": "1", "minWidth": "400px"}),
            ],
        ),
        # Team charts row 2
        html.Div(
            style={"display": "flex", "gap": "16px", "flexWrap": "wrap", "marginBottom": "24px"},
            children=[
                html.Div(dcc.Graph(id="team-model-pie"), style={"flex": "1", "minWidth": "400px"}),
                html.Div(
                    dash_table.DataTable(
                        id="team-table",
                        columns=[
                            {"name": "Username", "id": "username"},
                            {"name": "Sessions", "id": "sessions", "type": "numeric"},
                            {"name": "Input Tokens", "id": "input_tokens", "type": "numeric", "format": {"specifier": ","}},
                            {"name": "Output Tokens", "id": "output_tokens", "type": "numeric", "format": {"specifier": ","}},
                            {"name": "Cost (USD)", "id": "cost", "type": "numeric", "format": {"specifier": "$.4f"}},
                        ],
                        style_header={
                            "backgroundColor": REDIS_SECTION_BG, "color": REDIS_TEXT,
                            "fontWeight": "bold", "border": f"1px solid {REDIS_BORDER}",
                            "fontFamily": REDIS_FONT,
                        },
                        style_cell={
                            "backgroundColor": REDIS_CARD_BG, "color": REDIS_TEXT,
                            "border": f"1px solid {REDIS_BORDER}", "textAlign": "center",
                            "padding": "10px", "fontFamily": REDIS_FONT,
                        },
                        style_data_conditional=[
                            {"if": {"row_index": "odd"}, "backgroundColor": REDIS_SECTION_BG},
                        ],
                        page_size=20,
                    ),
                    style={"flex": "1", "minWidth": "400px"},
                ),
            ],
        ),
    ])


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
# Callback: Theme toggle
# ---------------------------------------------------------------------------
@app.callback(
    [Output("theme-store", "data"), Output("theme-toggle-btn", "children")],
    Input("theme-toggle-btn", "n_clicks"),
    State("theme-store", "data"),
    prevent_initial_call=True,
)
def toggle_theme(n_clicks, current_theme):
    new_theme = "light" if current_theme == "dark" else "dark"
    icon = "☀️" if new_theme == "dark" else "🌙"
    return new_theme, icon


# ---------------------------------------------------------------------------
# Callback: Apply theme to main container
# ---------------------------------------------------------------------------
@app.callback(
    [
        Output("main-container", "style"),
        Output("tab-content", "style"),
        Output("controls-bar", "style"),
        Output("header-title", "style"),
    ],
    Input("theme-store", "data"),
)
def apply_theme(theme):
    t = _theme_vals(theme)
    main_style = {
        "backgroundColor": t["bg"], "color": t["text"],
        "fontFamily": REDIS_FONT, "minHeight": "100vh", "padding": "24px",
    }
    tab_style = {"backgroundColor": t["bg"], "paddingTop": "20px"}
    controls_style = {
        "display": "flex", "justifyContent": "center", "alignItems": "center",
        "marginBottom": "20px", "gap": "12px", "flexWrap": "wrap",
        "backgroundColor": t["card_bg"], "borderRadius": "5px",
        "padding": "16px 24px", "border": f"1px solid {t['border']}",
    }
    header_style = {"textAlign": "center", "marginBottom": "0", "color": t["text"], "fontFamily": REDIS_FONT}
    return main_style, tab_style, controls_style, header_style


# ---------------------------------------------------------------------------
# Callback: Auto-refresh interval control
# ---------------------------------------------------------------------------
@app.callback(
    [Output("auto-refresh-interval", "interval"), Output("auto-refresh-interval", "disabled")],
    Input("auto-refresh-dropdown", "value"),
)
def set_auto_refresh(value):
    if value == "off":
        return 60_000, True
    return int(value) * 1000, False


# ---------------------------------------------------------------------------
# Callback: Refresh data (manual + auto)
# ---------------------------------------------------------------------------
@app.callback(
    [
        Output("refresh-trigger", "data"),
        Output("date-range", "min_date_allowed"),
        Output("date-range", "max_date_allowed"),
        Output("date-range", "start_date"),
        Output("date-range", "end_date"),
    ],
    [Input("refresh-btn", "n_clicks"), Input("auto-refresh-interval", "n_intervals")],
    prevent_initial_call=True,
)
def refresh_data(n_clicks, n_intervals):
    global df, pricing, tool_df
    df, pricing, tool_df = _load_and_prepare()
    min_date = df["finished_at"].min() if not df.empty else None
    max_date = df["finished_at"].max() if not df.empty else None
    return (n_clicks or 0) + (n_intervals or 0), min_date, max_date, min_date, max_date


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
        Output("hourly-heatmap", "figure"),
        Output("context-window", "figure"),
        Output("token-efficiency", "figure"),
        Output("burn-rate", "figure"),
        Output("session-duration", "figure"),
        Output("model-comparison", "figure"),
        Output("tool-usage-chart", "figure"),
        Output("session-data-table-container", "children"),
        Output("cost-session-table-container", "children"),
    ],
    [
        Input("date-range", "start_date"),
        Input("date-range", "end_date"),
        Input("refresh-trigger", "data"),
        Input("theme-store", "data"),
    ],
)
def update_dashboard(start_date, end_date, _refresh, theme):
    t = _theme_vals(theme or "dark")
    tpl = t["template"]
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
        ("input_tokens", "Input", REDIS_RED),
        ("output_tokens", "Output", "#8AB4C7"),
        ("cache_read_input_tokens", "Cache Read", REDIS_RED_HOVER),
    ]:
        y_vals = dff_plot[col].replace(0, np.nan)
        fig_time.add_trace(go.Scatter(
            x=dff_plot["finished_at"], y=y_vals, mode="lines", name=name,
            line=dict(color=color, width=1.5), connectgaps=False,
        ))
    fig_time.update_layout(
        template=tpl, title="Token Usage Over Time",
        xaxis_title="Time", yaxis_title="Tokens",
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
    filtered_colors = [REDIS_COLORWAY[i % len(REDIS_COLORWAY)] for i, c in enumerate(breakdown_cols)
                       if breakdown_sums[c.replace("_tokens", "").replace("_", " ").title()] > 0]
    fig_breakdown = go.Figure(go.Bar(
        x=filtered_values,
        y=filtered_labels,
        orientation="h",
        marker_color=filtered_colors if filtered_colors else [REDIS_RED],
    ))
    fig_breakdown.update_layout(
        template=tpl, title="Token Breakdown by Type",
        xaxis_title="Total Tokens", yaxis_title="",
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
        orientation="h", marker_color=REDIS_RED,
    ))
    fig_session.add_trace(go.Bar(
        y=session_totals.index.astype(str).str[:12],
        x=session_totals["output_tokens"], name="Output",
        orientation="h", marker_color="#8AB4C7",
    ))
    # Add cost as text annotation
    fig_session.update_layout(
        template=tpl, title="Top 20 Sessions by Total Tokens",
        barmode="stack", xaxis_title="Tokens", yaxis_title="Session",
        margin=dict(l=110, r=80, t=40, b=40), legend=dict(orientation="h", y=-0.15),
    )
    # Add cost annotations on the right side of bars
    for i, (sid, row) in enumerate(session_totals.iterrows()):
        fig_session.add_annotation(
            x=row["total"], y=str(sid)[:12],
            text=f" {_fmt_cost(row['cost_usd'])}",
            showarrow=False, xanchor="left",
            font=dict(color=REDIS_RED_HOVER, size=10),
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
        marker=dict(colors=REDIS_COLORWAY),
    ))
    fig_model.update_layout(
        template=tpl, title="Token Consumption by Model",
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
            line=dict(color=REDIS_RED, width=2),
            fill="tozeroy", fillcolor="rgba(255,68,56,0.15)",
        ))
    fig_cost_time.update_layout(
        template=tpl, title="Cumulative Estimated Cost Over Time",
        xaxis_title="Time", yaxis_title="Cost (USD)",
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
        marker_color=REDIS_RED,
        text=[_fmt_cost(v) for v in model_costs.values],
        textposition="auto",
    ))
    fig_cost_model.update_layout(
        template=tpl, title="Estimated Cost by Model",
        xaxis_title="Cost (USD)", yaxis_title="",
        margin=dict(l=140, r=20, t=40, b=40),
    )

    # --- 7. Cache efficiency (replace 0 with NaN) ---
    fig_cache = go.Figure()
    cache_read_vals = dff_plot["cache_read_input_tokens"].replace(0, np.nan)
    cache_create_vals = dff_plot["cache_creation_input_tokens"].replace(0, np.nan)
    fig_cache.add_trace(go.Scatter(
        x=dff_plot["finished_at"], y=cache_read_vals,
        mode="lines", name="Cache Read", line=dict(color="#8AB4C7", width=1.5),
        connectgaps=False,
    ))
    fig_cache.add_trace(go.Scatter(
        x=dff_plot["finished_at"], y=cache_create_vals,
        mode="lines", name="Cache Creation", line=dict(color=REDIS_RED_HOVER, width=1.5),
        connectgaps=False,
    ))
    fig_cache.update_layout(
        template=tpl, title="Cache Efficiency Over Time",
        xaxis_title="Time", yaxis_title="Tokens",
        margin=dict(l=50, r=20, t=40, b=40), legend=dict(orientation="h", y=-0.15),
    )

    # --- 8. Hourly Activity Heatmap ---
    fig_heatmap = go.Figure()
    if not dff.empty:
        dff_hm = dff.copy()
        dff_hm["hour"] = dff_hm["finished_at"].dt.hour
        dff_hm["dow"] = dff_hm["finished_at"].dt.dayofweek  # 0=Mon
        dow_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        hm_agg = dff_hm.groupby(["dow", "hour"])[["input_tokens", "output_tokens"]].sum()
        hm_agg["total"] = hm_agg["input_tokens"] + hm_agg["output_tokens"]
        hm_matrix = np.zeros((7, 24))
        for (dow, hour), row in hm_agg.iterrows():
            hm_matrix[dow, hour] = row["total"]
        fig_heatmap = go.Figure(go.Heatmap(
            z=hm_matrix, x=list(range(24)), y=dow_names,
            colorscale=[[0, t["bg"]], [0.5, t["section_bg"]], [1, REDIS_RED]],
            hovertemplate="Hour: %{x}<br>Day: %{y}<br>Tokens: %{z:,.0f}<extra></extra>",
        ))
    fig_heatmap.update_layout(
        template=tpl, title="Hourly Activity Heatmap",
        xaxis_title="Hour of Day", yaxis_title="",
        margin=dict(l=60, r=20, t=40, b=40),
    )

    # --- 9. Context Window Utilization ---
    fig_ctx = go.Figure()
    if not dff.empty:
        ctx_cols = ["input_tokens", "cache_read_input_tokens", "system_prompt_tokens",
                    "tool_definitions_tokens", "chat_history_tokens"]
        dff_ctx = dff[dff["max_context_tokens"] > 0].copy()
        if not dff_ctx.empty:
            dff_ctx["ctx_pct"] = dff_ctx[ctx_cols].sum(axis=1) / dff_ctx["max_context_tokens"] * 100
            fig_ctx.add_trace(go.Histogram(
                x=dff_ctx["ctx_pct"], nbinsx=50,
                marker_color=REDIS_RED, opacity=0.8,
                name="Exchanges",
            ))
            fig_ctx.add_vline(x=80, line_dash="dash", line_color=REDIS_RED_HOVER,
                              annotation_text="80% warning", annotation_font_color=REDIS_RED_HOVER)
    fig_ctx.update_layout(
        template=tpl, title="Context Window Utilization",
        xaxis_title="% Context Used", yaxis_title="Count",
        margin=dict(l=50, r=20, t=40, b=40),
    )

    # --- 10. Token Efficiency Ratio ---
    fig_efficiency = go.Figure()
    if not dff.empty:
        sess_eff = dff.groupby(["session_id", "model_id"])[["input_tokens", "output_tokens"]].sum().reset_index()
        sess_eff = sess_eff[(sess_eff["input_tokens"] > 0) & (sess_eff["output_tokens"] > 0)]
        if not sess_eff.empty:
            for model_id in sess_eff["model_id"].unique():
                mdf = sess_eff[sess_eff["model_id"] == model_id]
                fig_efficiency.add_trace(go.Scatter(
                    x=mdf["input_tokens"], y=mdf["output_tokens"],
                    mode="markers", name=model_id,
                    marker=dict(size=6, opacity=0.7),
                ))
            # Add 1:1 reference line
            max_val = max(sess_eff["input_tokens"].max(), sess_eff["output_tokens"].max())
            fig_efficiency.add_trace(go.Scatter(
                x=[0, max_val], y=[0, max_val],
                mode="lines", name="1:1 ratio",
                line=dict(color=REDIS_TEXT_MUTED, dash="dot", width=1),
                showlegend=True,
            ))
    fig_efficiency.update_layout(
        template=tpl, title="Token Efficiency (Input vs Output per Session)",
        xaxis_title="Total Input Tokens", yaxis_title="Total Output Tokens",
        margin=dict(l=60, r=20, t=40, b=40), legend=dict(orientation="h", y=-0.15),
    )

    # --- 11. Daily Burn Rate + Projection ---
    fig_burn = go.Figure()
    if not dff.empty:
        daily_cost = dff.set_index("finished_at").resample("D")["cost_usd"].sum().reset_index()
        daily_cost.columns = ["date", "cost"]
        daily_cost = daily_cost[daily_cost["cost"] > 0]
        if not daily_cost.empty:
            fig_burn.add_trace(go.Scatter(
                x=daily_cost["date"], y=daily_cost["cost"],
                mode="lines+markers", name="Daily Cost",
                line=dict(color=REDIS_RED, width=2),
                marker=dict(size=5),
            ))
            # Projection: 30 days from last date at average rate
            avg_daily = daily_cost["cost"].mean()
            last_date = daily_cost["date"].max()
            proj_dates = pd.date_range(last_date, periods=31, freq="D")
            proj_costs = [daily_cost["cost"].iloc[-1] if i == 0 else avg_daily for i in range(31)]
            fig_burn.add_trace(go.Scatter(
                x=proj_dates, y=proj_costs,
                mode="lines", name=f"Projection (avg ${avg_daily:.2f}/day)",
                line=dict(color=REDIS_RED_HOVER, dash="dash", width=2),
            ))
    fig_burn.update_layout(
        template=tpl, title="Daily Burn Rate + 30-Day Projection",
        xaxis_title="Date", yaxis_title="Cost (USD)",
        margin=dict(l=60, r=20, t=40, b=40), legend=dict(orientation="h", y=-0.15),
    )

    # --- 12. Session Duration Distribution ---
    fig_duration = go.Figure()
    if not dff.empty:
        sess_times = dff.groupby("session_id")["finished_at"].agg(["min", "max"])
        sess_times["duration_min"] = (sess_times["max"] - sess_times["min"]).dt.total_seconds() / 60
        sess_times = sess_times[sess_times["duration_min"] > 0]
        if not sess_times.empty:
            fig_duration.add_trace(go.Histogram(
                x=sess_times["duration_min"], nbinsx=40,
                marker_color="#8AB4C7", opacity=0.8,
                name="Sessions",
            ))
    fig_duration.update_layout(
        template=tpl, title="Session Duration Distribution",
        xaxis_title="Duration (minutes)", yaxis_title="Count",
        margin=dict(l=50, r=20, t=40, b=40),
    )

    # --- 13. Model Comparison: cost per 1K output tokens ---
    fig_model_comp = go.Figure()
    if not dff.empty:
        mc = dff.groupby("model_id").agg(total_cost=("cost_usd", "sum"), total_output=("output_tokens", "sum")).reset_index()
        mc = mc[mc["total_output"] > 0]
        if not mc.empty:
            mc["cost_per_1k"] = (mc["total_cost"] / mc["total_output"]) * 1000
            mc = mc.sort_values("cost_per_1k")
            fig_model_comp.add_trace(go.Bar(
                x=mc["model_id"], y=mc["cost_per_1k"],
                marker_color=REDIS_RED,
                text=[f"${v:.4f}" for v in mc["cost_per_1k"]],
                textposition="auto",
            ))
    fig_model_comp.update_layout(
        template=tpl, title="Cost per 1K Output Tokens by Model",
        xaxis_title="Model", yaxis_title="USD per 1K Output Tokens",
        margin=dict(l=60, r=20, t=40, b=40),
    )

    # --- 14. Tool Usage Analysis ---
    fig_tools = go.Figure()
    if not tool_df.empty:
        tool_agg = tool_df.groupby("tool_name")["count"].sum().sort_values(ascending=False).head(20)
        if not tool_agg.empty:
            fig_tools.add_trace(go.Bar(
                y=tool_agg.index[::-1], x=tool_agg.values[::-1],
                orientation="h", marker_color=REDIS_RED,
            ))
            fig_tools.update_layout(
                template=tpl, title="Top 20 Most-Used Tools",
                xaxis_title="Usage Count", yaxis_title="",
                margin=dict(l=200, r=20, t=40, b=40),
            )
        else:
            fig_tools.update_layout(
                template=tpl,
                annotations=[dict(text="Tool usage data not available", showarrow=False,
                                  font=dict(color=t["text_muted"], size=16), xref="paper", yref="paper", x=0.5, y=0.5)],
            )
    else:
        fig_tools.update_layout(
            template=tpl,
            annotations=[dict(text="Tool usage data not available", showarrow=False,
                              font=dict(color=t["text_muted"], size=16), xref="paper", yref="paper", x=0.5, y=0.5)],
        )

    # --- 15. Sortable Session Data Table ---
    table_style_header = {
        "backgroundColor": t["section_bg"], "color": t["text"],
        "fontWeight": "bold", "border": f"1px solid {t['border']}",
        "fontFamily": REDIS_FONT,
    }
    table_style_cell = {
        "backgroundColor": t["card_bg"], "color": t["text"],
        "border": f"1px solid {t['border']}", "textAlign": "center",
        "padding": "10px", "fontFamily": REDIS_FONT,
    }
    table_style_odd = [{"if": {"row_index": "odd"}, "backgroundColor": t["section_bg"]}]

    session_table_data = []
    if not dff.empty:
        for sid, grp in dff.groupby("session_id"):
            session_table_data.append({
                "session_id": str(sid)[:8],
                "model": grp["model_id"].iloc[0] or "",
                "created": str(grp["created"].iloc[0])[:19] if pd.notna(grp["created"].iloc[0]) else "",
                "exchanges": len(grp),
                "input_tokens": int(grp["input_tokens"].sum()),
                "output_tokens": int(grp["output_tokens"].sum()),
                "cache_tokens": int(grp["cache_read_input_tokens"].sum()),
                "cost": round(float(grp["cost_usd"].sum()), 4),
            })

    session_data_table = dash_table.DataTable(
        id="session-data-table",
        columns=[
            {"name": "Session ID", "id": "session_id"},
            {"name": "Model", "id": "model"},
            {"name": "Created", "id": "created"},
            {"name": "Exchanges", "id": "exchanges", "type": "numeric"},
            {"name": "Input Tokens", "id": "input_tokens", "type": "numeric", "format": {"specifier": ","}},
            {"name": "Output Tokens", "id": "output_tokens", "type": "numeric", "format": {"specifier": ","}},
            {"name": "Cache Tokens", "id": "cache_tokens", "type": "numeric", "format": {"specifier": ","}},
            {"name": "Cost (USD)", "id": "cost", "type": "numeric", "format": {"specifier": "$.4f"}},
        ],
        data=session_table_data,
        sort_action="native",
        filter_action="native",
        page_size=20,
        style_header=table_style_header,
        style_cell=table_style_cell,
        style_data_conditional=table_style_odd,
        style_table={"overflowX": "auto"},
    )

    # --- 16. Cost Per Session Breakdown Table ---
    cost_session_data = []
    if not dff.empty:
        sess_times = dff.groupby("session_id")["finished_at"].agg(["min", "max"])
        sess_times["duration_min"] = (sess_times["max"] - sess_times["min"]).dt.total_seconds() / 60
        for sid, grp in dff.groupby("session_id"):
            dur = round(sess_times.loc[sid, "duration_min"], 1) if sid in sess_times.index else 0
            cost_session_data.append({
                "session_id": str(sid)[:8],
                "model": grp["model_id"].iloc[0] or "",
                "duration_min": dur,
                "exchanges": len(grp),
                "input_tokens": int(grp["input_tokens"].sum()),
                "output_tokens": int(grp["output_tokens"].sum()),
                "cost": round(float(grp["cost_usd"].sum()), 4),
            })

    # Conditional formatting for cost > $5
    cost_conditional = list(table_style_odd) + [
        {
            "if": {"filter_query": "{cost} > 5", "column_id": "cost"},
            "color": REDIS_RED,
            "fontWeight": "bold",
        },
    ]

    cost_session_table = dash_table.DataTable(
        id="cost-session-table",
        columns=[
            {"name": "Session ID", "id": "session_id"},
            {"name": "Model", "id": "model"},
            {"name": "Duration (min)", "id": "duration_min", "type": "numeric"},
            {"name": "Exchanges", "id": "exchanges", "type": "numeric"},
            {"name": "Input Tokens", "id": "input_tokens", "type": "numeric", "format": {"specifier": ","}},
            {"name": "Output Tokens", "id": "output_tokens", "type": "numeric", "format": {"specifier": ","}},
            {"name": "Cost (USD)", "id": "cost", "type": "numeric", "format": {"specifier": "$.4f"}},
        ],
        data=cost_session_data,
        sort_action="native",
        filter_action="native",
        page_size=20,
        style_header=table_style_header,
        style_cell=table_style_cell,
        style_data_conditional=cost_conditional,
        style_table={"overflowX": "auto"},
    )

    return (
        subtitle,
        _fmt(n_sessions), _fmt(n_exchanges),
        _fmt(total_input), _fmt(total_output), _fmt(total_cache),
        _fmt_cost(total_cost),
        fig_time, fig_breakdown, fig_session, fig_model,
        fig_cost_time, fig_cost_model, fig_cache,
        fig_heatmap, fig_ctx, fig_efficiency, fig_burn, fig_duration,
        fig_model_comp, fig_tools,
        session_data_table, cost_session_table,
    )



# ---------------------------------------------------------------------------
# Callback: Daily/Weekly Summary (separate due to toggle)
# ---------------------------------------------------------------------------
@app.callback(
    Output("daily-weekly-summary", "figure"),
    [
        Input("date-range", "start_date"),
        Input("date-range", "end_date"),
        Input("refresh-trigger", "data"),
        Input("summary-toggle", "value"),
        Input("theme-store", "data"),
    ],
)
def update_daily_weekly(start_date, end_date, _refresh, period, theme):
    t = _theme_vals(theme or "dark")
    tpl = t["template"]
    dff = _filter(start_date, end_date)
    fig = go.Figure()
    freq = "D" if period == "daily" else "W"
    label = "Daily" if period == "daily" else "Weekly"
    if not dff.empty:
        grouped = dff.set_index("finished_at").resample(freq).agg(
            input_tokens=("input_tokens", "sum"),
            output_tokens=("output_tokens", "sum"),
            cost_usd=("cost_usd", "sum"),
        ).reset_index()
        grouped["total_tokens"] = grouped["input_tokens"] + grouped["output_tokens"]
        grouped = grouped[grouped["total_tokens"] > 0]
        if not grouped.empty:
            fig.add_trace(go.Bar(
                x=grouped["finished_at"], y=grouped["total_tokens"],
                name=f"{label} Tokens", marker_color=REDIS_RED, opacity=0.8,
                yaxis="y",
            ))
            fig.add_trace(go.Scatter(
                x=grouped["finished_at"], y=grouped["cost_usd"],
                name=f"{label} Cost", mode="lines+markers",
                line=dict(color="#8AB4C7", width=2),
                marker=dict(size=5), yaxis="y2",
            ))
            fig.update_layout(
                yaxis2=dict(
                    title="Cost (USD)", overlaying="y", side="right",
                    gridcolor=t["section_bg"], zerolinecolor=t["section_bg"],
                ),
            )
    fig.update_layout(
        template=tpl, title=f"{label} Token Usage & Cost",
        xaxis_title="Date", yaxis_title="Total Tokens",
        margin=dict(l=60, r=60, t=40, b=40), legend=dict(orientation="h", y=-0.15),
        barmode="overlay",
    )
    return fig


# ---------------------------------------------------------------------------
# Callback: Export data
# ---------------------------------------------------------------------------
@app.callback(
    Output("download-export", "data"),
    Input("export-btn", "n_clicks"),
    [State("date-range", "start_date"), State("date-range", "end_date")],
    prevent_initial_call=True,
)
def export_data(n_clicks, start_date, end_date):
    if not n_clicks:
        return no_update
    dff = _filter(start_date, end_date)
    # Build per-session summaries
    sessions_list = []
    for sid, grp in dff.groupby("session_id"):
        sessions_list.append({
            "session_id": sid,
            "model_id": grp["model_id"].iloc[0] if not grp.empty else None,
            "created": str(grp["created"].iloc[0]) if not grp.empty else None,
            "total_exchanges": len(grp),
            "input_tokens": int(grp["input_tokens"].sum()),
            "output_tokens": int(grp["output_tokens"].sum()),
            "cache_read_input_tokens": int(grp["cache_read_input_tokens"].sum()),
            "cost_usd": round(float(grp["cost_usd"].sum()), 6),
        })
    export_obj = {
        "username": USERNAME,
        "export_date": datetime.utcnow().isoformat() + "Z",
        "date_range": {"start": start_date, "end": end_date},
        "sessions": sessions_list,
        "totals": {
            "sessions": dff["session_id"].nunique(),
            "exchanges": len(dff),
            "input_tokens": int(dff["input_tokens"].sum()),
            "output_tokens": int(dff["output_tokens"].sum()),
            "cache_read_input_tokens": int(dff["cache_read_input_tokens"].sum()),
            "cost_usd": round(float(dff["cost_usd"].sum()), 6),
        },
    }
    date_str = datetime.utcnow().strftime("%Y%m%d")
    filename = f"augment-usage-{USERNAME}-{date_str}.json"
    return dict(content=json.dumps(export_obj, indent=2), filename=filename)


# ---------------------------------------------------------------------------
# Callback: Import team data
# ---------------------------------------------------------------------------
@app.callback(
    [Output("team-data-store", "data"), Output("import-status", "children")],
    Input("import-upload", "contents"),
    [State("import-upload", "filename"), State("team-data-store", "data")],
    prevent_initial_call=True,
)
def import_team_data(contents_list, filenames, existing_data):
    if not contents_list:
        return no_update, no_update
    if existing_data is None:
        existing_data = []
    imported_count = 0
    existing_usernames = {d.get("username") for d in existing_data}
    for content, fname in zip(contents_list, filenames):
        try:
            # Parse base64 content from dcc.Upload
            content_type, content_string = content.split(",", 1)
            decoded = base64.b64decode(content_string).decode("utf-8")
            data = json.loads(decoded)
            uname = data.get("username", fname)
            # Replace if same username already imported
            if uname in existing_usernames:
                existing_data = [d for d in existing_data if d.get("username") != uname]
            existing_data.append(data)
            existing_usernames.add(uname)
            imported_count += 1
        except Exception as e:
            continue
    total = len(existing_data)
    msg = f"✅ Imported {imported_count} file(s). Total team members loaded: {total}"
    return existing_data, msg


# ---------------------------------------------------------------------------
# Callback: Team tab charts
# ---------------------------------------------------------------------------
@app.callback(
    [
        Output("team-card-members", "children"),
        Output("team-card-sessions", "children"),
        Output("team-card-tokens", "children"),
        Output("team-card-cost", "children"),
        Output("team-cost-bar", "figure"),
        Output("team-tokens-bar", "figure"),
        Output("team-model-pie", "figure"),
        Output("team-table", "data"),
    ],
    [Input("team-data-store", "data"), Input("main-tabs", "value"), Input("theme-store", "data")],
)
def update_team_tab(team_data, active_tab, theme):
    t = _theme_vals(theme or "dark")
    tpl = t["template"]
    if active_tab != "team-usage" or not team_data:
        empty_fig = go.Figure()
        empty_fig.update_layout(
            template=tpl,
            annotations=[dict(text="Import team data to see charts", showarrow=False,
                              font=dict(color=t["text_muted"], size=16), xref="paper", yref="paper", x=0.5, y=0.5)],
        )
        return "0", "0", "0", "$0.00", empty_fig, empty_fig, empty_fig, []

    # Aggregate per-member data
    members = []
    model_usage = {}  # model -> total tokens
    for entry in team_data:
        uname = entry.get("username", "unknown")
        totals = entry.get("totals", {})
        members.append({
            "username": uname,
            "sessions": totals.get("sessions", 0),
            "input_tokens": totals.get("input_tokens", 0),
            "output_tokens": totals.get("output_tokens", 0),
            "cost": totals.get("cost_usd", 0),
        })
        # Aggregate model usage from sessions
        for sess in entry.get("sessions", []):
            model = sess.get("model_id", "unknown")
            tokens = sess.get("input_tokens", 0) + sess.get("output_tokens", 0)
            model_usage[model] = model_usage.get(model, 0) + tokens

    members_df = pd.DataFrame(members)
    total_members = len(members_df)
    total_sessions = int(members_df["sessions"].sum())
    total_tokens = int(members_df["input_tokens"].sum() + members_df["output_tokens"].sum())
    total_cost = float(members_df["cost"].sum())

    # Cost per member bar chart
    fig_cost = go.Figure(go.Bar(
        x=members_df["username"], y=members_df["cost"],
        marker_color=REDIS_RED,
        text=[_fmt_cost(v) for v in members_df["cost"]],
        textposition="auto",
    ))
    fig_cost.update_layout(
        template=tpl, title="Cost per Team Member",
        xaxis_title="", yaxis_title="Cost (USD)",
        margin=dict(l=60, r=20, t=40, b=40),
    )

    # Tokens per member (stacked bar)
    fig_tokens = go.Figure()
    fig_tokens.add_trace(go.Bar(
        x=members_df["username"], y=members_df["input_tokens"],
        name="Input", marker_color=REDIS_RED,
    ))
    fig_tokens.add_trace(go.Bar(
        x=members_df["username"], y=members_df["output_tokens"],
        name="Output", marker_color="#8AB4C7",
    ))
    fig_tokens.update_layout(
        template=tpl, title="Tokens per Team Member",
        barmode="stack", xaxis_title="", yaxis_title="Tokens",
        margin=dict(l=60, r=20, t=40, b=40), legend=dict(orientation="h", y=-0.15),
    )

    # Model usage pie chart
    model_labels = list(model_usage.keys())
    model_values = list(model_usage.values())
    fig_model = go.Figure(go.Pie(
        labels=model_labels, values=model_values, hole=0.45,
        textinfo="label+percent",
        marker=dict(colors=REDIS_COLORWAY),
    ))
    fig_model.update_layout(
        template=tpl, title="Model Usage Across Team",
        margin=dict(l=20, r=20, t=40, b=40),
    )

    table_data = members_df.to_dict("records")

    return (
        str(total_members), _fmt(total_sessions), _fmt(total_tokens), _fmt_cost(total_cost),
        fig_cost, fig_tokens, fig_model, table_data,
    )


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1")
    app.run(host=host, port=8050, debug=False)