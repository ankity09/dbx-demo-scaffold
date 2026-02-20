# Databricks Demo Scaffold

Reusable scaffold for building customer demos on Databricks. Clone this repo once, point vibe at it, and have a fully deployed demo in 2-4 hours.

**What's inside:** Battle-tested backend wiring (Lakebase auth/retry, MAS SSE streaming, health checks, action cards) extracted from production demos. You get the hard infrastructure for free — vibe generates the customer-specific story, UI, and data model.

**Stack:** FastAPI + Delta Lake + Lakebase (PostgreSQL) + MAS Agent Bricks + Genie Space + Databricks Apps. 100% serverless.

## Prerequisites

- [Databricks AI Dev Kit](https://github.com/databricks-solutions/ai-dev-kit) installed (MCP tools + skills)
- [Vibe](https://github.com/databricks-field-eng/vibe) (`vibe agent` CLI)
- Databricks CLI authenticated with a workspace profile

## Quick Start

### 1. Clone the scaffold (one-time)

```bash
git clone https://github.com/<your-org>/dbx-demo-scaffold.git ~/dbx-demo-scaffold
```

This is your **reference library** — don't build directly in this directory. Pull updates anytime with `git pull`.

### 2. Create a new demo

```bash
mkdir ~/demos/blue-origin-launch-ops && cd ~/demos/blue-origin-launch-ops
```

Name the folder whatever fits your demo. This will be a fresh project with its own git history.

### 3. Open in vibe and tell it what you want

```bash
vibe agent
```

Then say:

> Using the scaffold at ~/dbx-demo-scaffold, build me a launch operations demo for Blue Origin. They manage rocket engine test campaigns across 3 test facilities with 50+ engine units. Key use cases: test campaign scheduling, anomaly detection from sensor telemetry during hot-fire tests, and post-test analysis automation. I want a dark theme with a sidebar nav and a dashboard showing upcoming test schedules and engine health scores.

Vibe will:
1. Read the scaffold's `CLAUDE.md` and understand the 3-layer architecture
2. Copy the core modules (Lakebase pool, MAS streaming, health check) to your new project
3. Ask about your UI preferences if you didn't specify them
4. Generate the domain-specific data model, API routes, frontend pages, and agent prompts
5. Walk you through deployment (create workspace resources, run notebooks, deploy app)

### 4. Initialize git in your new project

```bash
git init
git add .
git commit -m "Initial scaffold: Blue Origin Launch Ops demo"
```

## How It Works

The scaffold has 3 layers:

| Layer | What | Who Touches It |
|-------|------|----------------|
| **CORE** | Lakebase auth/retry, MAS SSE streaming, health checks, input validation | Nobody — battle-tested, never modify |
| **SKELETON** | `app.yaml`, schema templates, notebook stubs, agent config templates | Vibe fills in the placeholders |
| **CUSTOMER** | Dashboard, domain pages, API routes, data model, agent prompts, talk track | Vibe generates from scratch based on your prompt |

### What you get for free (CORE)

- **Lakebase connection pool** with OAuth token refresh and automatic retry on stale connections
- **MAS SSE streaming** proxy with sub-agent step indicators, action card detection, and follow-up suggestions
- **Health endpoint** that checks SDK, SQL warehouse, and Lakebase connectivity
- **Chat interface** with full streaming UI, typing indicators, and inline AI analysis
- **Agent Workflows page** with workflow cards, centered modal with animated agent orchestration diagram, approve/dismiss/ask AI
- **21 documented gotchas** so vibe doesn't repeat mistakes that cost hours to debug

### What vibe builds (CUSTOMER)

- App layout and color scheme (based on your preference)
- Dashboard with domain-specific KPIs, charts, and tables
- Domain pages (inventory, shipments, test schedules, etc.)
- Backend API routes for your domain data
- Delta Lake tables and Lakebase schemas
- Data generation notebooks with realistic synthetic data
- MAS agent prompts and Genie Space configuration
- Talk track and demo narrative

## Using with AI Dev Kit

This scaffold is designed to work alongside [Databricks AI Dev Kit](https://github.com/databricks-solutions/ai-dev-kit):

| Tool | What It Does | Example |
|------|-------------|---------|
| **AI Dev Kit MCP tools** | Execute Databricks operations | Create catalogs, run SQL, deploy apps, manage Lakebase |
| **AI Dev Kit skills** | Teach vibe Databricks patterns | Correct SDP syntax, Lakebase auth patterns, dashboard best practices |
| **This scaffold** | Provide pre-wired app code | Lakebase pool, MAS streaming, chat UI, workflow management |

AI Dev Kit is the **how you build** (tools + knowledge). This scaffold is the **what you build from** (starting code). Together, vibe can go from a prompt to a deployed demo without you writing a line of code.

## Project Structure

```
dbx-demo-scaffold/
├── CLAUDE.md                    # Architecture, patterns, gotchas (vibe reads this)
├── README.md                    # You're here
├── app/
│   ├── app.yaml                 # Deployment config (fill placeholders)
│   ├── requirements.txt         # Pinned dependencies
│   ├── backend/
│   │   ├── core/                # NEVER MODIFY — battle-tested wiring
│   │   │   ├── lakehouse.py     # Delta Lake queries via Statement Execution API
│   │   │   ├── lakebase.py      # PostgreSQL pool with OAuth token refresh
│   │   │   ├── streaming.py     # MAS SSE streaming + action card detection
│   │   │   ├── health.py        # 3-check health endpoint
│   │   │   └── helpers.py       # Input validation, response parsing
│   │   └── main.py              # App assembly (vibe adds domain routes)
│   └── frontend/src/
│       └── index.html           # Starter: Chat + Agent Workflows (vibe adds pages)
├── lakebase/
│   ├── core_schema.sql          # Required tables (notes, agent_actions, workflows)
│   └── domain_schema.sql        # Domain-specific tables (vibe generates)
├── lakebase-mcp-server/         # Standalone MCP server for agent writes (16 tools)
├── notebooks/
│   ├── 01_setup_schema.sql      # Create catalog/schema
│   ├── 02_generate_data.py      # Generate Delta Lake tables
│   └── 03_seed_lakebase.py      # Seed Lakebase operational tables
├── agent_bricks/                # MAS + KA config templates
├── genie_spaces/                # Genie Space config template
└── examples/
    └── supply_chain_routes.py   # Reference: all route patterns from a production demo
```

## Example Prompts

**Predictive Maintenance (dark industrial theme)**
> Using the scaffold at ~/dbx-demo-scaffold, build me a predictive maintenance demo for Apex Steel. 5 factories, 200+ CNC machines, IoT sensors. I want anomaly detection, work order automation, and spare parts optimization. Dark industrial theme with sidebar nav.

**Launch Operations (space/aerospace theme)**
> Using the scaffold at ~/dbx-demo-scaffold, build me a launch operations demo for Blue Origin. 3 test facilities, 50+ engine units, sensor telemetry during hot-fire tests. I want test campaign scheduling, anomaly detection, and post-test analysis. Dark theme with a dashboard showing test schedules and engine health.

**Financial Risk (corporate theme)**
> Using the scaffold at ~/dbx-demo-scaffold, build me a credit risk demo for First National Bank. 50K loan portfolio, real-time risk scoring. I want a corporate blue theme, dashboard-first layout with portfolio breakdown charts, and AI-powered what-if analysis.

## Updating the Scaffold

```bash
cd ~/dbx-demo-scaffold
git pull
```

Existing demos are not affected — they have their own copies of the core modules. To update an existing demo's core modules, copy the new files manually or tell vibe to update them.

## License

Internal use — Databricks Field Engineering.
