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

### 3. Open in vibe and run the setup wizard

```bash
vibe agent
```

Then run the **`/new-demo`** slash command:

```
/new-demo
```

The wizard walks you through 5 phases:

| Phase | What it does | Time |
|-------|-------------|------|
| **1. Customer Discovery** | You provide the customer website + Salesforce UCO (or business problem). Vibe researches the company, extracts brand colors, finds industry challenges, and proposes a customer-specific demo story. | 5 min |
| **2. Infrastructure** | Workspace URL, CLI profile, catalog, schema, warehouse ID | 3 min |
| **3. Data Model** | Entities and KPIs tailored to the customer's actual business (informed by Phase 1 research) | 5 min |
| **4. AI Layer** | Genie tables, MAS persona, sub-agents, MCP server | 3 min |
| **5. UI** | Layout, brand colors (auto-extracted from customer website), dashboard content, pages | 3 min |

After each phase, your answers are saved to `demo-config.yaml` so nothing is lost. At the end, you'll see a full summary to approve before any code is generated.

**Why the research step matters:** Instead of building a generic "manufacturing demo," vibe builds a demo that references the customer's actual products, facilities, challenges, and brand. The demo feels like it was built *for them*.

Once approved, vibe will:
1. Copy the core modules (Lakebase pool, MAS streaming, health check) to your project
2. Fill in all config files with your answers (no TODOs left behind)
3. Generate the data model, API routes, frontend pages, and agent prompts
4. Walk you through deployment (create workspace resources, run notebooks, deploy app)

**Already know what you want?** You can skip the wizard and give vibe a direct prompt instead:

> Using the scaffold at ~/dbx-demo-scaffold, build me a launch operations demo for Blue Origin. They manage rocket engine test campaigns across 3 test facilities with 50+ engine units. Key use cases: test campaign scheduling, anomaly detection from sensor telemetry during hot-fire tests, and post-test analysis automation. I want a dark theme with a sidebar nav and a dashboard showing upcoming test schedules and engine health scores.

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
├── .claude/commands/
│   └── new-demo.md              # /new-demo wizard — 5-phase guided setup
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
├── skill/                       # AI Dev Kit skill (knowledge docs)
│   ├── SKILL.md                 # Skill definition
│   └── resources/               # Lakebase, Apps, data gen reference docs
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
