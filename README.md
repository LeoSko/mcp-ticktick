<div align="center">

# mcp-ticktick

**Your TickTick workflows — available to any AI.**

[![PyPI](https://img.shields.io/pypi/v/mcp-ticktick?style=flat-square)](https://pypi.org/project/mcp-ticktick/)
[![Python](https://img.shields.io/pypi/pyversions/mcp-ticktick?style=flat-square)](https://pypi.org/project/mcp-ticktick/)
[![License](https://img.shields.io/github/license/karbassi/mcp-ticktick?style=flat-square)](LICENSE)
[![CI](https://img.shields.io/github/actions/workflow/status/karbassi/mcp-ticktick/ci.yml?style=flat-square&label=tests)](https://github.com/karbassi/mcp-ticktick/actions)

A [Model Context Protocol](https://modelcontextprotocol.io/) server that gives LLMs broad access to [TickTick](https://ticktick.com).<br>
Tasks, projects, habits, focus timers, tags, filters, and calendars.

**53 tools** · **4 resources** · **Broad TickTick coverage**

</div>

---

## Quick Start

```bash
pip install mcp-ticktick
mcp-ticktick login
```

The login command walks you through creating a TickTick OAuth app, then accepts
either the browser's `t` cookie value or a copied Cookie request header. It stores
both credentials locally in one run. Then add the server to your AI client of
choice:

<details>
<summary><strong>Claude Desktop</strong></summary>

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "ticktick": {
      "command": "mcp-ticktick"
    }
  }
}
```

</details>

<details>
<summary><strong>Claude Code</strong></summary>

```bash
claude mcp add mcp-ticktick -- mcp-ticktick
```

Stored OAuth and browser-session credentials are loaded automatically.

</details>

<details>
<summary><strong>Cursor</strong></summary>

Add to `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "ticktick": {
      "command": "mcp-ticktick"
    }
  }
}
```

</details>

<details>
<summary><strong>Windsurf</strong></summary>

Add to `~/.codeium/windsurf/mcp_config.json`:

```json
{
  "mcpServers": {
    "ticktick": {
      "command": "mcp-ticktick"
    }
  }
}
```

</details>

<details>
<summary><strong>VS Code / GitHub Copilot</strong></summary>

Add to your VS Code `settings.json`:

```json
{
  "mcp": {
    "servers": {
      "ticktick": {
        "command": "mcp-ticktick"
      }
    }
  }
}
```

</details>

## What Can It Do?

> *"Add a task to my Shopping list due tomorrow"*  
> *"Check in my meditation habit for today"*  
> *"Show me what I focused on this week"*  
> *"Move all tasks tagged #backlog to the Archive project"*

| Domain | Tools | Highlights |
|---|---|---|
| **Tasks** | 18 | Create, edit, complete, delete, move, comments, subtasks, trash, batch changes |
| **Projects** | 5 | CRUD with fuzzy name matching |
| **Tags** | 6 | Create, rename, merge, hierarchies |
| **Folders** | 4 | Group projects into folders |
| **Habits** | 8 | Track, check in, streaks, sections |
| **Filters** | 4 | Saved custom filters |
| **Focus** | 5 | Pomodoro records, stats, session history |
| **Calendar** | 3 | Connected calendars and events |

Plus 4 read-only **resources**: `ticktick://profile` · `ticktick://settings` · `ticktick://projects` · `ticktick://tags`

<details>
<summary><strong>Full tool reference</strong></summary>

### Tasks

| Tool | Description |
|---|---|
| `list_tasks` | List tasks from a project or all projects |
| `get_task` | Get a single task by ID |
| `list_task_comments` | List comments for a task |
| `add_task_comment` | Add a comment to a task |
| `edit_task_comment` | Edit a task comment |
| `delete_task_comment` | Delete a task comment |
| `add_task` | Create a task with due date, priority, tags, checklist |
| `add_tasks` | Create multiple tasks in one MCP call |
| `edit_task` | Update task fields |
| `edit_tasks` | Update multiple task fields in one batch request |
| `complete_task` | Mark a task complete |
| `delete_task` | Delete a task |
| `delete_tasks` | Delete multiple tasks in one MCP call |
| `move_task` | Move a task between projects |
| `set_subtask` | Make a task a subtask of another |
| `set_subtasks` | Make multiple tasks subtasks in one batch request |
| `unparent_task` | Remove a task from its parent |
| `list_trash` | List deleted tasks |

Task comment tools require the browser-session `t` cookie because TickTick
exposes comments through the private v2 web API. `list_task_comments` returns
TickTick's stable comment IDs plus author and timestamp metadata such as
`userProfile`, `createdTime`, and `modifiedTime`. Editing is supported by
TickTick's web API and replaces the comment text while preserving existing
comment metadata:

```text
list_task_comments(task_id="...", project="Inbox")
add_task_comment(task_id="...", project="Inbox", text="Waiting for invoice")
edit_task_comment(task_id="...", project="Inbox", comment_id="...", text="Invoice received")
delete_task_comment(task_id="...", project="Inbox", comment_id="...")
```

`add_task`, `add_tasks`, `edit_task`, and `edit_tasks` accept `reminders`.
Use official TickTick trigger strings, bare ISO-8601 durations, or compact
before-due offsets:

```text
add_task(title="Call dentist", due="2027-03-01T15:00", reminders=["30m", "PT0S"])
add_task(title="Passport", due="2027-03-01", reminders=["TRIGGER:P0DT9H0M0S"])
edit_task(task_id="...", project="Inbox", reminders=["1h"])
edit_task(task_id="...", project="Inbox", clear_reminders=true)
```

Official trigger examples include `TRIGGER:PT0S` for the task time,
`TRIGGER:-PT30M` for 30 minutes before, and `TRIGGER:P0DT9H0M0S` for a 9:00
all-day reminder. Compact offsets such as `30m`, `1h`, and `1d` are converted
to before-due triggers.

`add_task`, `add_tasks`, `edit_task`, and `edit_tasks` also accept recurring
task rules through `repeat`. Use RFC 5545 RRULE strings with the `RRULE:`
prefix. Supported frequencies are `DAILY`, `WEEKLY`, `MONTHLY`, and `YEARLY`,
with common parts such as `INTERVAL`, `COUNT`, `UNTIL`, `BYDAY`,
`BYMONTHDAY`, `BYMONTH`, and `WKST`:

```text
add_task(title="Standup", due="2027-03-01T09:00", repeat="RRULE:FREQ=WEEKLY;INTERVAL=1;BYDAY=MO,WE,FR", timezone="Europe/Stockholm")
edit_task(task_id="...", project="Inbox", repeat="RRULE:FREQ=MONTHLY;INTERVAL=1")
edit_task(task_id="...", project="Inbox", clear_repeat=true)
```

Recurring tasks require a start or due date. `repeat_from` currently supports
the due-date origin only (`due_date` or `1`), which is the TickTick web default
verified for create and edit. Completion-date repeat origins and per-instance
recurrence exceptions are not exposed yet because TickTick represents them
through generated occurrence state that has not been validated as a stable
standalone API.

The same task tools accept IANA timezone names such as `America/Chicago` and
`Europe/Stockholm`. The package includes the IANA timezone database for systems
without one, including Windows. Pass `timezone` with an all-day date to preserve
the intended local calendar date:

```text
add_task(title="Test", due="2027-03-01", all_day=true, timezone="America/Chicago")
```

### Projects

| Tool | Description |
|---|---|
| `list_projects` | List all projects |
| `get_project` | Get a project by name or ID (fuzzy match) |
| `add_project` | Create a new project |
| `edit_project` | Update project properties |
| `delete_project` | Delete a project and its tasks |

### Tags

| Tool | Description |
|---|---|
| `list_tags` | List all tags |
| `add_tags` | Create one or more tags |
| `delete_tags` | Delete tags |
| `rename_tag` | Rename a tag (updates all tasks) |
| `edit_tag` | Update tag color, parent, sort |
| `merge_tags` | Merge one tag into another |

### Folders

| Tool | Description |
|---|---|
| `list_folders` | List all project folders |
| `add_folder` | Create a folder |
| `delete_folders` | Delete folders |
| `rename_folder` | Rename a folder |

### Habits

| Tool | Description |
|---|---|
| `list_habits` | List all habits |
| `add_habit` | Create a boolean or numeric habit |
| `edit_habit` | Update habit properties |
| `delete_habits` | Delete habits |
| `checkin_habit` | Record a habit check-in |
| `habit_log` | Query check-in history |
| `archive_habits` | Archive habits (hide, keep data) |
| `manage_habit_sections` | List, add, delete, rename sections |

### Filters

| Tool | Description |
|---|---|
| `list_filters` | List saved filters |
| `add_filter` | Create a filter |
| `edit_filter` | Update a filter |
| `delete_filters` | Delete filters |

### Focus

| Tool | Description |
|---|---|
| `focus_status` | Current timer status |
| `focus_stats` | Daily and total focus statistics |
| `focus_log` | Focus sessions for a date range |
| `focus_timeline` | Full session history |
| `focus_save` | Save a completed pomodoro record |

### Calendar

| Tool | Description |
|---|---|
| `list_calendars` | List connected calendar accounts |
| `list_events` | Query events for a date range |
| `sync_account` | Full account sync |

</details>

## Authentication

The server uses two separate TickTick credentials:

- **OAuth** for TickTick's official v1 task and project API.
- A browser **`t` session cookie** for private v2/v3 features such as tags,
  folders, filters, habits, focus, calendars, checkpoint sync, and reliable task
  edits.

### OAuth login

Create a free TickTick [OAuth app](https://developer.ticktick.com/manage) and
register `http://127.0.0.1:8080/callback` as its redirect URL. Then run:

```bash
mcp-ticktick login
```

The command prints the setup steps, prompts for the app's client ID and secret,
opens TickTick authorization in your browser, validates the loopback callback,
and exchanges the authorization code. It then prompts for the browser session
cookie and stores both credentials at
`~/.config/mcp-ticktick/credentials.json` with owner-only permissions.

Use `--no-browser` to print the authorization URL without opening it, or
`--credentials-file PATH` to choose another credential file. Use
`--skip-session` for OAuth-only setup.

### Browser session cookie

To enable private v2/v3 features:

1. Sign in at [ticktick.com](https://ticktick.com) and open browser developer
   tools.
2. In **Network**, select an `api.ticktick.com` request and copy its Cookie
   request header. Alternatively, copy the value of `t` from
   **Application/Storage → Cookies**.
3. Return to the waiting `mcp-ticktick login` prompt and paste what you copied.

The login flow extracts `t` from a full Cookie header and adds it to the same
owner-only credential file without overwriting OAuth credentials. The standalone
`mcp-ticktick session` command refreshes an expired cookie without repeating
OAuth. For scripts, pipe the value or header to
`mcp-ticktick session --stdin`.

The cookie expires independently; repeat the session step when the server reports
that the v2 session is invalid. Treat it like a password: do not commit it, paste
it into issues, or include it in logs.

### Environment overrides

Environment variables take precedence over stored OAuth credentials.

| Variable | Required | Description |
|---|---|---|
| `TICKTICK_ACCESS_TOKEN` | No | Override the stored OAuth access token |
| `TICKTICK_CLIENT_ID` | No | Override the stored OAuth client ID |
| `TICKTICK_CLIENT_SECRET` | No | Override the stored OAuth client secret |
| `TICKTICK_REFRESH_TOKEN` | No | OAuth refresh token, when issued |
| `TICKTICK_CREDENTIALS_FILE` | No | Override the OAuth credential file path |
| `TICKTICK_V2_SESSION_TOKEN` | No | Override the stored browser `t` cookie used by v2 and v3 |

Project, folder, filter, and tag reads share a process-local cache refreshed through
the v3 checkpoint sync endpoint, so unchanged account data is not downloaded again.

## HTTP transport

No arguments runs the stdio transport used by local MCP clients. For Streamable HTTP:

```bash
mcp-ticktick serve --transport http --host 127.0.0.1 --port 8000
```

The MCP endpoint is `http://127.0.0.1:8000/mcp`. Legacy SSE is available with
`--transport sse` at `/sse`. `TICKTICK_MCP_TRANSPORT`, `TICKTICK_MCP_HOST`, and
`TICKTICK_MCP_PORT` provide equivalent defaults.

> HTTP transport has no authentication in this server. Keep the default loopback
> binding, or place it behind a TLS-enabled authenticating reverse proxy before
> exposing it to a network.

## Development

```bash
git clone https://github.com/karbassi/mcp-ticktick.git
cd ticktick-mcp
uv sync --all-extras
uv run ruff check src/ tests/
uv run pytest
```

## License

[MIT](LICENSE)
