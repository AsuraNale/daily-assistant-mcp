---
name: daily-assistant
description: "AI-powered daily task management MCP Server — recommend next task, inherit uncompleted todos, detect overdue, generate reviews. Deterministic ops in code (zero tokens), AI only when needed."
version: 1.0.0
metadata:
  openclaw:
    requires:
      bins:
        - python3
    emoji: "📅"
    homepage: https://github.com/AsuraNale/daily-assistant-mcp
---

# Daily Assistant MCP Server

A personal task management MCP Server. Deterministic operations (parsing, sorting, statistics) run in Python with zero token cost — AI only steps in when creativity is needed.

## Setup

```bash
git clone https://github.com/AsuraNale/daily-assistant-mcp.git
cd daily-assistant-mcp
pip install fastmcp
python3 src/setup.py   # Windows: py src/setup.py
```

The setup wizard creates your data directory and config. Then add to `.mcp.json`:

```json
{
  "mcpServers": {
    "daily-assistant": {
      "command": "python3",
      "args": ["-X", "utf8", "/path/to/daily-assistant-mcp/src/server.py"]
    }
  }
}
```

## Tools

| Tool | What it does |
|------|-------------|
| `recommend_next` | Recommends the most important task to work on next |
| `get_today` | Reads today's daily task file |
| `inherit_tasks` | Carries over uncompleted tasks from yesterday |
| `check_overdue` | Detects overdue task files |
| `generate_review` | Generates end-of-day review with completion stats |
| `scan_split` | Flags tasks >80min or missing time estimates |

## Resources

| Resource | Content |
|----------|---------|
| `daily://today` | Today's task file |
| `daily://dashboard` | Dashboard overview |
| `daily://history` | 7-day completion statistics |

## Task Format

```markdown
- [ ] Task description ⏱️45min 📅 2026-03-30 ⏫
```

Markers: `⏱️` = time estimate, `📅` = deadline, `⏫` = highest priority, `🔼` = high, `🔽` = low.

## Design Philosophy

- **Zero-token deterministic ops**: Parsing, sorting, stats run in Python code
- **AI only when needed**: Task splitting, creative advice, context-aware suggestions
- **Platform-independent**: Windows, macOS, Linux. No Obsidian dependency
- **Simple data**: Plain Markdown files, edit anywhere
