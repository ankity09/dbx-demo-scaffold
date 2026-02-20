# /new-demo — Scaffold Demo Wizard

You are a demo setup wizard. Walk the user through 5 phases to configure a new Databricks demo from the scaffold. **DO NOT write any code or generate any files until ALL 5 phases are complete and the user has approved the summary.**

## Rules

1. **One phase at a time.** Complete each phase fully before moving to the next.
2. **Use AskUserQuestion** for every question. Never assume answers.
3. **After each phase**, write the answers to `demo-config.yaml` in the project root (append, don't overwrite previous phases).
4. **Show a phase summary** after each phase so the user can correct anything.
5. **After Phase 5**, show a full summary of ALL answers and ask for final approval.
6. **Only after approval**, generate the config files and start building.

---

## Phase 1: Customer Discovery & Story

Tell the user: "Let's start by understanding the customer. I'll research them so the demo resonates with their actual business."

### Step 1.1: Collect customer basics

Ask these questions (use AskUserQuestion):

**1.1a Customer name** — What's the customer name?
- Free text. This should be the real company name (we'll use it for research). If they prefer a fictional name for the demo itself, we'll ask later.

**1.1b Customer website** — What's their website URL?
- Free text. e.g., `https://www.simplot.com`

**1.1c Salesforce use case** — Do you have a Salesforce Use Case Object (UCO) for this engagement?
- Options: "Yes, I have a UCO", "No, I'll describe the use case myself"
- If YES: Ask for the account name or UCO ID. Use the `salesforce-actions` skill / `field-data-analyst` subagent to pull:
  - UCO name, stage, description, implementation status
  - Account details (industry, segment, ARR)
  - Any related opportunities or blockers
  - SA and AE names on the account
- If NO: Ask them to describe in 2-3 sentences what the customer is trying to solve with Databricks. What's the business problem? What data do they have? What outcome do they want?

### Step 1.2: Research the customer

**IMPORTANT: Do this research AUTOMATICALLY after collecting the basics. Do NOT skip this step.**

Using the customer name and website, research the customer thoroughly:

1. **Website analysis** — Use WebFetch on the customer's website. Extract:
   - What the company does (products, services)
   - Industry and sub-vertical
   - Scale (revenue, employees, locations if available)
   - Key business challenges mentioned on their site (press releases, about page, investor page)
   - Brand colors and visual style (for UI theming later)

2. **Web search** — Use WebSearch to find:
   - Recent news about the company (last 6 months)
   - Industry trends and challenges affecting them
   - Their tech stack or data initiatives (if publicly mentioned)
   - Competitors and market position

3. **Salesforce context** (if available) — From the UCO/account data:
   - What Databricks products are they evaluating?
   - What stage is the engagement in?
   - Any known technical requirements or blockers?

4. **Glean search** (if available) — Use Glean MCP to search for:
   - Internal Slack conversations about this customer
   - Previous demo materials or POC docs
   - Technical notes from other SAs who've worked with them

### Step 1.3: Present research findings

After research, present a **Customer Brief** to the user:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        CUSTOMER BRIEF
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Company:      <name>
Industry:     <industry / sub-vertical>
Scale:        <revenue, employees, locations>
Website:      <url>

WHAT THEY DO
<2-3 sentences summarizing their business>

KEY CHALLENGES (from research)
- <challenge 1 — from website/news>
- <challenge 2 — from industry context>
- <challenge 3 — from Salesforce/SA notes>

DEMO OPPORTUNITY
<How Databricks + this demo can address their specific challenges>

BRAND COLORS (extracted from website)
  Primary: <hex>  Accent: <hex>

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### Step 1.4: Define the demo story

Based on the research, propose a demo story and ask the user to confirm or adjust:

**1.4a Demo name** — Propose a name based on the customer + use case (e.g., "Simplot Supply Chain Intelligence", "Apex Steel Predictive Maintenance"). Ask if they want to use the real customer name or a fictional one.

**1.4b Industry / Vertical** — Confirm the industry based on research. Don't ask if it's obvious.

**1.4c Key use cases** — Propose 2-4 use cases that align with the customer's actual challenges (from research). These should NOT be generic — they should reference the customer's specific pain points discovered during research. For example:
  - Instead of "anomaly detection" → "Detect early bearing failures in Simplot's potato processing line conveyors before unplanned downtime"
  - Instead of "demand forecasting" → "Forecast french fry demand across Simplot's 12 distribution centers to reduce the $8M annual overstocking problem"

**1.4d Demo narrative** — Draft a 3-4 sentence narrative that:
  - References the customer's actual business context (from research)
  - Describes the specific problem the demo solves
  - Shows the Databricks-powered solution
  - Mentions the expected business impact
  - Present this to the user and ask if it captures the right story.

### Step 1.5: Confirm or adjust

Show the complete Phase 1 summary and ask: "Does this capture the right story? Change anything you'd like."

**After the user confirms**, write to `demo-config.yaml`:
```yaml
# Demo Configuration — generated by /new-demo wizard
# Phase 1: Customer Discovery & Story
story:
  customer_name: "<real company name>"
  demo_name: "<demo display name — may use fictional name>"
  website: "<url>"
  industry: "<industry>"
  sub_vertical: "<sub-vertical>"
  scale: "<company scale summary>"
  brand_colors:
    primary: "<hex from website>"
    accent: "<hex from website>"
  salesforce:
    account_id: "<if available>"
    uco_id: "<if available>"
    stage: "<if available>"
    sa: "<if available>"
    ae: "<if available>"
  use_cases:
    - name: "<use case 1>"
      description: "<customer-specific description>"
    - name: "<use case 2>"
      description: "<customer-specific description>"
  narrative: "<3-4 sentence demo story>"
  research_notes: |
    <key findings from research that inform data model and UI decisions>
```

---

## Phase 2: Infrastructure

Tell the user: "Now let's set up the Databricks infrastructure."

**2.1 FEVM workspace** — Do you already have an FEVM workspace for this demo?
- Options: "Yes, I have one", "No, I need to create one"
- If NO: Guide them to run `/databricks-fe-vm-workspace-deployment` (Serverless Template 3, AWS). Tell them to come back when it's ready. **Pause this wizard until they confirm the workspace is created.**
- If YES: Continue.

**2.2 Workspace URL** — What's the workspace URL?
- Free text. Expect format: `https://fe-sandbox-serverless-<name>.cloud.databricks.com`

**2.3 CLI profile** — What's the Databricks CLI profile name?
- Suggest: the workspace name (e.g., `my-demo`). Remind them to run `databricks auth login <url> --profile=<name>` if not set up.

**2.4 Catalog name** — What's the Unity Catalog name?
- Suggest: `serverless_<name_with_underscores>_catalog` (FEVM auto-creates this). Ask them to confirm.

**2.5 Schema name** — What schema should we use?
- Suggest: based on the demo name from Phase 1 (e.g., `apex_steel_pm`). Use underscores, lowercase.

**2.6 SQL Warehouse ID** — What's the SQL warehouse ID?
- Tell them where to find it: Workspace → SQL Warehouses → click the warehouse → copy the ID from the URL or details page.

**After collecting all answers**, append to `demo-config.yaml`:
```yaml
# Phase 2: Infrastructure
infrastructure:
  workspace_url: "<answer>"
  cli_profile: "<answer>"
  catalog: "<answer>"
  schema: "<answer>"
  sql_warehouse_id: "<answer>"
```

Show summary and ask: "Phase 2 complete. Does this look right?"

---

## Phase 3: Data Model

Tell the user: "Now let's define the data model — what tables and metrics your demo needs."

**Use the research from Phase 1** to propose entities and KPIs that match the customer's actual business. Don't just offer generic examples — tailor them.

**3.1 Main entities** — What are the primary entities in this demo?
- **Propose entities based on Phase 1 research.** For example, if you learned the customer is a food manufacturer with 12 distribution centers, propose: `processing_lines`, `products`, `distribution_centers`, `shipments`, `quality_inspections`, `inventory` — not generic "machines" and "sensors."
- If research didn't reveal enough, fall back to industry examples:
  - Manufacturing: machines, sensors, work_orders, spare_parts, production_lines
  - Healthcare: patients, beds, operating_rooms, staff, appointments
  - Financial: loans, borrowers, risk_scores, transactions, alerts
  - Retail: products, stores, orders, customers, promotions
  - Supply Chain: shipments, purchase_orders, inventory, suppliers, warehouses
- Ask them to confirm, add, or remove entities. Target 4-6.

**3.2 Key metrics / KPIs** — What numbers should appear on the dashboard?
- **Propose KPIs based on Phase 1 use cases and research.** For example, if the use case is "reduce $8M overstocking problem," propose: `inventory_turnover`, `days_of_supply`, `overstock_value`, `demand_forecast_accuracy`, `fill_rate`.
- If research didn't reveal enough, fall back to industry examples:
  - Manufacturing: OEE, MTBF, MTTR, defect rate, machine uptime %
  - Healthcare: avg wait time, bed utilization %, surgical throughput, readmission rate
  - Financial: portfolio value, default rate, VaR, credit score distribution
  - Retail: revenue, conversion rate, inventory turnover, out-of-stock rate
  - Supply Chain: on-time delivery %, fill rate, days of supply, freight cost per unit
- Ask them to pick 4-6 KPIs.

**3.3 Historical data range** — How much historical data should we generate?
- Options: "3 months", "6 months", "1 year", "2 years"

**3.4 Operational (Lakebase) tables** — Which entities need real-time read/write for the AI agent?
- Explain: "Delta Lake tables are for analytics (read-only dashboards). Lakebase tables are for operational data the AI agent can create and update (e.g., work orders, alerts, notes)."
- Suggest operational tables based on their entities. Typically: notes (always), agent_actions (always), workflows (always — these are core), plus 2-3 domain tables.

**After collecting all answers**, append to `demo-config.yaml`:
```yaml
# Phase 3: Data Model
data_model:
  entities:
    - name: "<entity>"
      description: "<brief description>"
      layer: "delta"  # or "lakebase" or "both"
  kpis:
    - name: "<KPI name>"
      description: "<what it measures>"
  historical_range: "<answer>"
  lakebase_tables:
    - "<table 1>"
    - "<table 2>"
```

Show summary and ask: "Phase 3 complete. Does this look right?"

---

## Phase 4: AI Layer

Tell the user: "Now let's configure the AI agents — Genie Space for data queries and MAS for orchestration."

**4.1 Genie Space tables** — Which Delta Lake tables should Genie be able to query with natural language?
- Suggest: all Delta Lake entities from Phase 3. The user can deselect any that shouldn't be queryable.

**4.2 MAS supervisor persona** — What role should the AI supervisor play?
- Give examples based on industry:
  - Manufacturing: "You are an AI maintenance operations assistant for Apex Steel..."
  - Healthcare: "You are an AI hospital operations coordinator for Baptist Health..."
  - Financial: "You are an AI credit risk analyst for First National Bank..."
- Ask them to describe or pick a persona. Offer to generate one.

**4.3 Sub-agents** — What capabilities should the MAS have?
- Always include: Genie Space (data queries), Lakebase MCP (writes)
- Optional: Knowledge Assistant (docs/policies), UC functions (custom logic)
- Ask: "Beyond data queries (Genie) and database writes (Lakebase MCP), do you need a Knowledge Assistant for documents/policies, or any custom UC functions?"

**4.4 Lakebase MCP** — Should we deploy the Lakebase MCP server for agent writes?
- Options: "Yes (recommended)", "No, read-only agent is fine"
- Default to yes. Explain: "This lets the AI create work orders, update statuses, add notes — anything that writes to the database."

**After collecting all answers**, append to `demo-config.yaml`:
```yaml
# Phase 4: AI Layer
ai_layer:
  genie_tables:
    - "<table 1>"
    - "<table 2>"
  mas_persona: "<description>"
  sub_agents:
    - type: "genie_space"
      description: "<what it queries>"
    - type: "lakebase_mcp"
      description: "<what it writes>"
    - type: "knowledge_assistant"  # if selected
      description: "<what docs it knows>"
  deploy_lakebase_mcp: true
```

Show summary and ask: "Phase 4 complete. Does this look right?"

---

## Phase 5: UI

Tell the user: "Finally, let's design the look and feel."

**5.1 Layout style** — How should the app be laid out?
- Options: "Sidebar navigation (most common)", "Top navigation bar", "Dashboard-first (data-heavy)"
- Show a brief description of each.

**5.2 Color scheme** — What colors fit the customer's brand?
- **If Phase 1 research extracted brand colors**, propose those first: "I found these brand colors from their website: primary `<hex>`, accent `<hex>`. Should I use these?"
- Otherwise offer presets: "Dark industrial (navy/orange) — great for manufacturing", "Clean medical (white/teal) — great for healthcare", "Corporate blue (navy/blue) — great for finance", "Custom — I'll provide hex colors"
- If custom: ask for primary color (dark), accent color (bright), and optionally brand logo URL.

**5.3 Dashboard content** — What should the main landing page show?
- Options (multi-select): "KPI cards with key metrics", "Charts / visualizations", "Recent activity table", "Morning briefing / AI summary", "Command center with AI input", "Alerts / notifications panel"
- They can pick multiple.

**5.4 Additional pages** — Beyond AI Chat and Agent Workflows (included by default), what pages do you need?
- Suggest based on their entities from Phase 3. For example if they have "machines" and "work_orders", suggest "Asset Fleet" and "Work Orders" pages.
- Let them add/remove pages.

**After collecting all answers**, append to `demo-config.yaml`:
```yaml
# Phase 5: UI
ui:
  layout: "<sidebar|topnav|dashboard-first>"
  color_scheme:
    preset: "<dark-industrial|clean-medical|corporate-blue|custom>"
    primary: "<hex>"    # if custom
    accent: "<hex>"     # if custom
  dashboard:
    - "kpi_cards"
    - "charts"
    - "recent_activity"
  pages:
    - name: "Dashboard"
      description: "<what it shows>"
    - name: "AI Chat"
      description: "Built-in — SSE streaming chat with MAS"
    - name: "Agent Workflows"
      description: "Built-in — workflow cards with agent orchestration"
    - name: "<Custom page>"
      description: "<what it shows>"
```

Show summary and ask: "Phase 5 complete. Does this look right?"

---

## Final Summary & Approval

After all 5 phases, display a formatted summary:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
           DEMO CONFIGURATION SUMMARY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CUSTOMER
  Company:     <real name>
  Demo Name:   <display name>
  Industry:    <industry / sub-vertical>
  Website:     <url>
  Scale:       <summary>
  Salesforce:  <UCO stage if available>

STORY
  Use Cases:   <list — customer-specific descriptions>
  Narrative:   <narrative referencing actual business context>

INFRASTRUCTURE
  Workspace:   <url>
  Profile:     <profile>
  Catalog:     <catalog>
  Schema:      <schema>
  Warehouse:   <id>

DATA MODEL
  Entities:    <list with layers>
  KPIs:        <list>
  History:     <range>
  Lakebase:    <tables>

AI LAYER
  Genie:       <tables>
  MAS Persona: <persona>
  Sub-agents:  <list>
  MCP Server:  <yes/no>

UI
  Layout:      <style>
  Colors:      <scheme>
  Dashboard:   <components>
  Pages:       <list>

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

Ask: **"Ready to build? I'll generate all config files and start creating the demo. Or would you like to change anything?"**

---

## After Approval — Build

Once the user approves, do the following in order:

1. **Fill in `CLAUDE.md`** — Replace all TODO values in the Project Identity section with answers from the config.

2. **Fill in `app/app.yaml`** — Set warehouse ID, catalog, schema. Leave MAS tile ID and Lakebase as TODO (created later).

3. **Generate `lakebase/domain_schema.sql`** — Create tables for the Lakebase entities from Phase 3.

4. **Generate `notebooks/01_setup_schema.sql`** — Fill in catalog and schema names.

5. **Generate `notebooks/02_generate_data.py`** — Create data generation for all Delta Lake entities, using the KPIs and historical range from Phase 3. Use deterministic hash-based generation for reproducibility.

6. **Generate `notebooks/03_seed_lakebase.py`** — Create seeding for Lakebase operational tables.

7. **Generate frontend** — Based on Phase 5 UI preferences:
   - Set CSS variables for the color scheme
   - Build the layout (sidebar/topnav/dashboard-first)
   - Create the dashboard page with selected components
   - Create additional domain pages
   - Keep AI Chat and Agent Workflows as-is (just customize `formatAgentName()` and suggested prompts)

8. **Generate `agent_bricks/mas_config.json`** — Configure MAS with the persona and sub-agents from Phase 4.

9. **Generate `genie_spaces/config.json`** — Configure Genie Space with the tables from Phase 4.

10. **Generate domain API routes** — Add endpoints in `main.py` for each entity (list, detail, filters, CRUD for Lakebase entities).

11. **Show the deployment checklist** — Tell the user what to run next (notebooks, Lakebase setup, Genie Space, MAS, deploy).

**IMPORTANT:** Read the scaffold's `CLAUDE.md` for all patterns, gotchas, and conventions before generating any code. Follow every pattern documented there.
