# OpenClaw → Hermes Cron Migration Playbook

Playbook used to migrate the ironclaw-jobs agent. Apply same pattern for remaining agents (ironclaw, ironclaw-seo, ironclaw-edu).

## Pattern

For each pipeline, follow this sequence:

### 1. Audit the source

```bash
# List OpenClaw agents and their cron jobs
ls ~openclaw/ironclaw-data/agents/
sudo -u openclaw cat ~openclaw/ironclaw-data/cron/jobs.json | python3 -m json.tool

# Check active state
sudo -u openclaw openclaw cron list

# Get full job spec
sudo -u openclaw openclaw cron get <job-id>
```

### 2. Create a Hermes skill

Consolidate all agent knowledge (SOUL.md, TOOLS.md, AGENTS.md, bootcamp profiles, templates) into one Hermes skill:

```
~/.hermes/skills/<category>/<name>/SKILL.md
```

Templates go under `templates/`, scripts under `scripts/`, reference data under `references/`.

### 3. Create Hermes cron jobs

**Critical**: create jobs under the main profile (not a dedicated one) to avoid profile-scoping issues:

```python
cronjob(
    action="create",
    name="Name: Descriptive",
    schedule="0 10 * * 3",  # cron expression
    skills=["skill-name"],   # load the skill
    model={"model":"deepseek-v4-flash","provider":"deepseek"},  # cheaper model
    deliver="slack:CHANNEL_ID",  # Slack delivery
    prompt="..."  # self-contained prompt
)
```

Profile-scoping gotcha: jobs created under a different profile only fire when that profile's gateway runs. The main gateway handles only default-profile jobs. Use `model` override for cost savings instead.

### 4. Disable the OpenClaw cron job

```bash
sudo -u openclaw openclaw cron disable <job-id>
```

Disable only the jobs for the pipeline being migrated. Leave other agents' jobs running.

### 5. Verify Hermes picks it up

```bash
hermes cron status  # should show new jobs
cronjob(action="list")  # verify delivery targets
```

### 6. Test with manual trigger

```bash
hermes cron run <job-id>  # trigger immediately
hermes cron status  # check run status
```

### 7. Cut over only when proven

After the Hermes job runs successfully at least once on schedule:
- Confirm Slack delivery works
- Confirm S3 uploads work (if applicable)
- Then proceed to next pipeline

### 8. Gateway management

- Hermes gateway must be running for cron: `hermes gateway install` → `hermes gateway start`
- Both gateways can coexist (Hermes on 18790, OpenClaw on 18789)
- When ready to fully decommission OpenClaw: `sudo -u openclaw systemctl --user stop openclaw-gateway`, remove service file at `~openclaw/.config/systemd/user/openclaw-gateway.service`
- Cron watcher processes may need manual kill: `ps aux | grep "openclaw cron" | grep -v grep`

## Key decisions made

- **DeepSeek over Z.AI**: User prefers DeepSeek provider for Hermes
- **v4-flash for cron**: Cheap model ($0.27/$1.10 per M tokens) sufficient for classification/summary tasks
- **Incremental migration**: One pipeline at a time, verify, then next
- **Wednesday cadence**: User's preference for job scrape cycle (12:00 staleness, 14:00 scrape, 16:00 reports CET)
