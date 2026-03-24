# Augment Token Usage Dashboard

A Python Dash dashboard that visualizes your Augment AI token consumption and estimated costs. Reads session data from `~/.augment/sessions/` and displays interactive charts.

## Features

- **Redis-branded UI** — dark/light theme with Redis brand colors, Space Grotesk/Mono fonts
- **Token usage tracking** — input, output, cache read, cache creation tokens over time
- **Cost estimation** — estimated USD costs using live pricing from [llm-prices.com](https://www.llm-prices.com/)
- **Model breakdown** — token consumption and cost by model (Claude Opus, Sonnet, Haiku)
- **Model comparison** — cost per 1K output tokens across models
- **Session analysis** — top sessions by token usage with cost annotations
- **Cache efficiency** — cache read vs creation patterns
- **Daily/weekly summary** — aggregated token and cost trends
- **Hourly activity heatmap** — when you use Augment most (hour × day of week)
- **Context window utilization** — how close you get to the 204K token limit
- **Token efficiency ratio** — output-to-input ratio per session by model
- **Daily burn rate** — daily cost with 30-day projection
- **Session duration** — distribution of session lengths
- **Sortable data tables** — full session list and cost breakdown with search/filter
- **Date range filtering** — filter all charts by date range
- **Dark/light theme toggle** — switch between Redis dark and light themes
- **Auto-refresh** — configurable auto-refresh interval (1/5/15 min)
- **Live refresh** — reload session data without restarting
- **Export/Import** — export your usage data as JSON, import team members' data
- **Team view** — aggregated team usage tab with per-member breakdown
- **Docker support** — one-command deployment with docker compose

## Screenshots

### Dashboard Overview (Dark Theme)
![Header, summary cards, and controls](screenshots/redis-header-cards.png)

### Token Usage & Breakdown
![Token usage over time and breakdown by type](screenshots/redis-token-charts.png)

### Sessions & Model Analysis
![Top sessions and model usage pie chart](screenshots/redis-sessions-models.png)

### Model Comparison & Tool Usage
![Cost per 1K output tokens and tool usage](screenshots/redis-model-comparison.png)

### Cost Analysis
![Cumulative cost and cost by model](screenshots/redis-cost-charts.png)

### Cache Efficiency
![Cache read vs creation over time](screenshots/redis-cache-efficiency.png)

### Daily Summary & Heatmap
![Daily token/cost summary and hourly activity heatmap](screenshots/redis-daily-summary.png)

### Context Window & Token Efficiency
![Context utilization histogram and efficiency scatter plot](screenshots/redis-heatmap-context.png)

### Burn Rate & Token Efficiency
![Daily burn rate projection and token efficiency ratio](screenshots/redis-efficiency-burnrate.png)

### Session Duration
![Session duration distribution](screenshots/redis-session-duration.png)

### Cost Per Session Table
![Sortable cost breakdown table with conditional formatting](screenshots/redis-cost-table.png)

### Session Data Table
![Full session data table with search and filter](screenshots/redis-session-table.png)

### Light Theme
![Dashboard in light theme mode](screenshots/redis-light-theme.png)

## Quick Start

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run the dashboard
python app.py
```

Open <[http://localhost:8050](http://localhost:8050)>

### Docker

```bash
docker compose up --build
```

Open <[http://localhost:8050](http://localhost:8050)>

The Docker setup automatically:

- Mounts `~/.augment/sessions/` read-only into the container
- Detects your username from the host
- Exposes the dashboard on port 8050

## Team Usage Workflow

1. Each team member runs the dashboard and clicks **📤 Export My Data**
2. They share their `augment-usage-{username}-{date}.json` file
3. The team lead clicks **📥 Import Team Data** and uploads all files
4. Switch to the **Team Usage** tab to see aggregated stats

## Data Source

The dashboard reads Augment session files from `~/.augment/sessions/*.json`. Each file contains chat history with token usage metadata per LLM call.

## Configuration

| Environment Variable | Default | Description |
| --- | --- | --- |
| AUGMENT_SESSIONS_DIR | ~/.augment/sessions | Path to session files |
| AUGMENT_USERNAME | Auto-detected from home dir | Username shown in dashboard |
| HOST | 127.0.0.1 | Bind address (0.0.0.0 for Docker) |

## ⚠️ Security & Privacy

**This dashboard exposes sensitive data.** Be aware of the following:

- **Session data contains your full conversation history** with Augment AI, including code snippets, file paths, and potentially secrets or credentials that appeared in your prompts
- **The exported JSON files** contain per-session token summaries (no conversation content), but do include your username and session IDs
- **The dashboard binds to **`127.0.0.1`** (localhost only) by default** — it is NOT accessible from other machines on your network
- **In Docker mode**, the compose file sets `HOST=0.0.0.0` — if your machine's firewall allows it, the dashboard could be accessible on your local network. The session data volume is mounted read-only
- **Do not deploy this to a public server** — there is no authentication, and the session data directory would be exposed
- **Exported team data files** should be shared through secure channels (not public Slack channels, not email without encryption)

**TL;DR**: Run locally only. Don't expose to the internet. Treat exported files as confidential.

## Tech Stack

- [Dash](https://dash.plotly.com/) 4.0 — Python web framework
- [Plotly](https://plotly.com/python/) 6.6 — Interactive charts
- [Pandas](https://pandas.pydata.org/) 2.2 — Data processing
- [llm-prices](https://github.com/simonw/llm-prices) — LLM pricing data

## License

MIT