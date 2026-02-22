# Databricks Demo Scaffold

Reusable scaffold for building customer demos on Databricks. Clone this repo once, point vibe at it, and have a fully deployed demo in 2-4 hours.

**What's inside:** Battle-tested backend wiring (Lakebase auth/retry, MAS SSE streaming, health checks, action cards) extracted from production demos. You get the hard infrastructure for free — vibe generates the customer-specific story, UI, and data model.

**Stack:** FastAPI + Delta Lake + Lakebase (PostgreSQL) + MAS Agent Bricks + Genie Space + Databricks Apps. 100% serverless.

## Prerequisites

You must use this scaffold through **Vibe agent** (the Databricks enterprise Claude Code environment). Personal Claude Code subscriptions won't have the required plugins and internal MCP tools.

### 1. Vibe agent

Vibe is the Databricks Field Engineering wrapper around Claude Code. It provides the enterprise plugins (Salesforce, Glean, Slack, Jira, Google Workspace) and internal MCP servers that the `/new-demo` wizard uses for customer research.

```bash
# Install vibe (if not already installed)
# Follow instructions at: https://github.com/databricks-field-eng/vibe

# Verify it works
vibe agent
```

After installation, run `vibe agent` once and follow the setup prompts. This will:
- Create `~/.vibe/profile` with your SA identity
- Install enterprise plugins to `~/.vibe/marketplace/`
- Configure MCP servers for Glean, Slack, Jira, and Confluence in `~/.claude/mcp.json`
- Set up Chrome DevTools MCP for UI testing

### 2. Databricks AI Dev Kit

The AI Dev Kit provides the Databricks MCP server — this is how vibe creates Genie Spaces, runs SQL, deploys apps, and manages Lakebase programmatically.

```bash
# Clone and install
git clone https://github.com/databricks-solutions/ai-dev-kit.git ~/ai-dev-kit
cd ~/ai-dev-kit
python -m venv .venv
source .venv/bin/activate
pip install -e databricks-mcp-server/

# Verify the MCP server can start
python databricks-mcp-server/run_server.py --help
```

The global MCP config (`~/.claude/mcp.json`) should already reference this after vibe setup. If not, add:
```json
{
  "mcpServers": {
    "databricks": {
      "command": "~/ai-dev-kit/.venv/bin/python",
      "args": ["~/ai-dev-kit/databricks-mcp-server/run_server.py"],
      "env": { "DATABRICKS_CONFIG_PROFILE": "DEFAULT" }
    }
  }
}
```

### 3. Databricks CLI

The CLI is used for workspace authentication and direct operations (Lakebase psql, app deployment, resource management).

```bash
# Install (if not already installed)
brew install databricks/tap/databricks

# Authenticate with a workspace
databricks auth login https://fe-sandbox-serverless-<name>.cloud.databricks.com --profile=<name>

# Verify
databricks current-user me --profile=<name>
```

You'll create a workspace-specific profile during the `/new-demo` wizard (Phase 2). If you don't have a workspace yet, the wizard will guide you through creating one via FEVM.

### 4. Verify everything

Run these checks before starting your first demo:

```bash
# Vibe agent starts and shows enterprise plugins
vibe agent
# You should see fe-databricks-tools, fe-salesforce-tools, etc. in the skill list

# Databricks CLI is authenticated
databricks current-user me --profile=<your-profile>

# AI Dev Kit MCP server exists
ls ~/ai-dev-kit/databricks-mcp-server/run_server.py
```

### What each component provides

| Component | What it gives the scaffold | Without it |
|-----------|---------------------------|-----------|
| **Vibe agent** | Enterprise plugins (Salesforce, Glean, Slack), internal MCP servers, SA identity | Phase 1 research is limited to web search only — no Salesforce UCO lookup, no internal Slack/Glean search |
| **AI Dev Kit** | Databricks MCP tools (execute_sql, create apps, manage Genie/MAS) | Phase 8 deployment must be done manually via CLI commands |
| **Databricks CLI** | Workspace auth, Lakebase psql, app deployment, resource management | Can't authenticate or run deployment commands |

## Quick Start

### 1. Clone the scaffold (one-time)

```bash
git clone https://github.com/ankity09/dbx-demo-scaffold.git ~/dbx-demo-scaffold
```

Pull updates anytime with `git pull`.

### 2. Open vibe in the scaffold directory

```bash
cd ~/dbx-demo-scaffold
vibe agent
```

**Important:** Open vibe from the scaffold directory — the `/new-demo` slash command lives in `.claude/commands/` and is only visible when vibe is opened here.

### 3. Run the setup wizard

```
/new-demo
```

The wizard walks you through 9 phases (Phase 0-8) — from project setup to deployed app — all within a single command:

| Phase | What it does | Time |
|-------|-------------|------|
| **0. Project Setup** | Creates a separate project directory so the scaffold stays clean. Copies scaffold files, initializes git. Handles resume detection if you restart. | 1 min |
| **1. Customer Discovery** | SA context interview (skippable questions), then automated two-pass research via web + Salesforce + Glean + Slack. Accepts direct Salesforce URLs. Extracts brand colors, cross-references use case keywords, and proposes a customer-specific demo story. | 5-8 min |
| **2. Infrastructure** | Workspace URL, CLI profile, catalog, schema, warehouse ID | 3 min |
| **3. Data Model** | Entities and KPIs tailored to the customer's actual business (informed by Phase 1 research) | 5 min |
| **4. AI Layer** | Genie tables, MAS persona, sub-agents, MCP server | 3 min |
| **5. UI** | Layout, brand colors (auto-extracted from customer website), dashboard content, pages | 3 min |
| **6. Plan & Approve** | Vibe enters plan mode — shows you exactly what files will be created and how. You approve before any code is generated. | 3 min |
| **7. Build** | Code generation (parallelized with sub-agents for speed). Creates your new project directory with all files. | 5-10 min |
| **8. Deploy** | 4-phase deployment: Delta Lake data → Lakebase → AI Layer → App Deploy. Verifies health and reports the final app URL. | 15-20 min |

After each Q&A phase (1-5), your answers are saved to `demo-config.yaml` so nothing is lost.

**Why the research step matters:** Instead of building a generic "manufacturing demo," vibe builds a demo that references the customer's actual products, facilities, challenges, and brand. For example, if you say "Simplot + genomics," vibe searches `site:simplot.com genomics` to find what Simplot is actually doing with genomics, then uses that context to build a demo that feels like it was built *for them*.

**Already know what you want?** You can skip the wizard and give vibe a direct prompt instead:

> Build me a launch operations demo for Blue Origin. They manage rocket engine test campaigns across 3 test facilities with 50+ engine units. Key use cases: test campaign scheduling, anomaly detection from sensor telemetry during hot-fire tests, and post-test analysis automation. I want a dark theme with a sidebar nav and a dashboard showing upcoming test schedules and engine health scores.

### 4. Start building

Phase 0 creates your project in a separate directory (e.g., `~/demos/blue-origin-launch-ops/`) and initializes git automatically. After Phase 2, you'll restart vibe in the new project directory to pick up MCP tools — the wizard resumes where you left off.

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

## Slash Commands

The scaffold includes 4 slash commands (visible when vibe is opened in this directory):

| Command | What it does |
|---------|-------------|
| **`/new-demo`** | Full setup wizard — 9 phases from project setup to deployed app. This is the main entry point. |
| **`/deploy-demo`** | Quick redeploy after code changes. Syncs files, checks resources, deploys, verifies health. |
| **`/demo-health`** | Run diagnostics on a deployed demo. Checks app status, resources, health endpoint, and offers automatic fixes. |
| **`/demo-talk-track`** | Generate a structured talk track / demo script for presenting to the customer. |

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
│   ├── new-demo.md              # /new-demo wizard — 9-phase guided setup
│   ├── deploy-demo.md           # /deploy-demo — quick redeploy after changes
│   ├── demo-health.md           # /demo-health — diagnostics & auto-fix
│   └── demo-talk-track.md       # /demo-talk-track — generate presentation script
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
├── docs/
│   ├── API_PATTERNS.md          # Genie, MAS, UC HTTP connection API reference
│   ├── DEPLOYMENT_GUIDE.md      # Deployment sequence reference
│   ├── FRONTEND_PATTERNS.md     # Frontend conventions
│   └── GOTCHAS.md               # Known issues and workarounds
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
