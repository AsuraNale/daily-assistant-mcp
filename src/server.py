"""
日常小助手 MCP Server — Phase 3（独立化版本）

自包含 MCP Server：core.py + config.json，不依赖 Obsidian。
通过 stdio 连接 Claude Code / OpenClaw。

Tools (6):
  - recommend_next  — 推荐下一步行动
  - get_today       — 读取今日待办
  - inherit_tasks   — 继承昨日未完成任务
  - check_overdue   — 检测超期任务
  - generate_review — 生成日终回顾
  - scan_split      — 检测需要拆分的大任务

Resources (3):
  - daily://today     — 今日待办内容
  - daily://dashboard — Dashboard 面板内容
  - daily://history   — 最近 7 天完成统计

用法:
    py -X utf8 server.py
    py -X utf8 server.py --config path/to/config.json
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

from fastmcp import FastMCP

from core import (
    parse_task, rank_tasks, format_recommendation,
    PRIORITY_LABEL, format_deadline_label,
    scan_overdue_files,
    find_latest_daily, extract_uncompleted_tasks, create_today_file,
    parse_all_tasks, generate_review as _generate_review_text,
    scan_split_needed,
)


# ============================================================
# 配置加载
# ============================================================

def load_config(config_path: Path = None) -> dict:
    """
    加载配置文件。搜索顺序：
    1. 显式传入的路径
    2. server.py 同目录下的 config.json
    """
    if config_path and config_path.exists():
        return json.loads(config_path.read_text(encoding="utf-8"))

    default = Path(__file__).parent / "config.json"
    if default.exists():
        return json.loads(default.read_text(encoding="utf-8"))

    raise FileNotFoundError(
        "找不到 config.json。请在 server.py 同目录下放置 config.json，"
        "或用 --config 指定路径。"
    )


# 解析命令行 --config 参数
_config_path = None
if "--config" in sys.argv:
    idx = sys.argv.index("--config")
    if idx + 1 < len(sys.argv):
        _config_path = Path(sys.argv[idx + 1])

_config = load_config(_config_path)

DAILY_DIR = Path(_config["daily_dir"])
DASHBOARD_FILE = Path(_config.get("dashboard_file", str(DAILY_DIR.parent / "Dashboard.md")))


# ============================================================
# MCP Server 定义
# ============================================================

mcp = FastMCP(
    name="日常小助手",
    instructions="""你是一个个人任务管理助手。
通过 MCP tools 可以读取用户的每日待办、推荐下一步行动、继承任务、检测超期、生成回顾。
确定性操作（读取/排序/统计）由 tool 完成，零 token 消耗。
只在用户需要 AI 创造力时（如任务拆分、卡住求建议）才需要你的推理能力。

可用 tools:
- recommend_next: 推荐下一步该做什么
- get_today: 读取今日待办文件
- inherit_tasks: 将昨天未完成的任务继承到今天
- check_overdue: 检测所有超期任务
- generate_review: 生成日终回顾并写入文件
- scan_split: 检测需要拆分的大任务（>80min 或缺预估时间）

可用 resources:
- daily://today: 今日待办内容
- daily://dashboard: Dashboard 面板
- daily://history: 最近 7 天完成统计"""
)


# ============================================================
# Tools
# ============================================================

@mcp.tool()
def recommend_next(date: str = "") -> str:
    """推荐用户接下来应该做什么任务。

    扫描指定日期的 Daily 文件中的未完成任务，
    按优先级和 deadline 排序，返回最应该做的任务及行动建议。

    Args:
        date: 日期，格式 YYYY-MM-DD。留空则默认今天。
    """
    today = datetime.strptime(date, "%Y-%m-%d") if date else datetime.now()
    today_str = today.strftime("%Y-%m-%d")
    today_file = DAILY_DIR / f"{today_str}.md"

    if not today_file.exists():
        return f"⚠️ 今日待办文件不存在: {today_str}.md\n先运行 inherit_tasks 或手动创建今日文件。"

    content = today_file.read_text(encoding="utf-8")
    tasks = [parse_task(line, today) for line in content.split("\n")]
    tasks = [t for t in tasks if t]

    if not tasks:
        has_completed = any(
            l.strip().startswith("- [x] ") for l in content.split("\n")
        )
        if has_completed:
            return "🎉 今日任务清零！所有任务都已完成，干得漂亮！"
        else:
            return f"📝 今日还没有添加任务。打开 Daily/{today_str}.md 添加今天的任务吧。"

    ranked = rank_tasks(tasks)
    return format_recommendation(ranked, today)


@mcp.tool()
def get_today(date: str = "") -> str:
    """读取指定日期的 Daily 待办文件完整内容。

    Args:
        date: 日期，格式 YYYY-MM-DD。留空则默认今天。
    """
    today = datetime.strptime(date, "%Y-%m-%d") if date else datetime.now()
    today_str = today.strftime("%Y-%m-%d")
    today_file = DAILY_DIR / f"{today_str}.md"

    if not today_file.exists():
        return f"⚠️ 文件不存在: Daily/{today_str}.md"

    content = today_file.read_text(encoding="utf-8")
    return f"📄 Daily/{today_str}.md\n\n{content}"


@mcp.tool()
def inherit_tasks(date: str = "") -> str:
    """将前一天未完成的任务继承到指定日期的 Daily 文件中。

    如果目标日期的 Daily 文件已存在，则不会覆盖。

    Args:
        date: 目标日期，格式 YYYY-MM-DD。留空则默认今天。
    """
    today = datetime.strptime(date, "%Y-%m-%d") if date else datetime.now()
    today_str = today.strftime("%Y-%m-%d")
    today_file = DAILY_DIR / f"{today_str}.md"

    if today_file.exists():
        return f"⚠️ 今日文件已存在: {today_str}.md，不会覆盖。"

    latest = find_latest_daily(DAILY_DIR, before_date=today)

    if not latest:
        create_today_file(DAILY_DIR, today, [], None)
        return f"📭 未找到之前的待办文件。已创建空白的 {today_str}.md。"

    uncompleted = extract_uncompleted_tasks(latest)

    if not uncompleted:
        create_today_file(DAILY_DIR, today, [], None)
        return f"🎉 {latest.name} 中所有任务已完成！已创建空白的 {today_str}.md。"

    source_date = latest.stem
    create_today_file(DAILY_DIR, today, uncompleted, source_date)

    task_list = "\n".join(f"  {t}" for t in uncompleted)
    return (
        f"✅ 已创建 {today_str}.md\n"
        f"继承自: {latest.name}\n"
        f"继承任务数: {len(uncompleted)}\n\n"
        f"{task_list}"
    )


@mcp.tool()
def check_overdue(date: str = "") -> str:
    """检测所有超期的 Daily 文件（日期已过但仍有未完成任务）。

    Args:
        date: 当前日期，格式 YYYY-MM-DD。留空则默认今天。
    """
    today = datetime.strptime(date, "%Y-%m-%d") if date else datetime.now()
    today_str = today.strftime("%Y-%m-%d")

    overdue = scan_overdue_files(DAILY_DIR, today)

    if not overdue:
        return f"✅ 没有超期任务（截至 {today_str}），所有待办都已完成！"

    total_tasks = sum(len(item["uncompleted"]) for item in overdue)
    lines = [f"⚠️ 发现 {len(overdue)} 个超期文件，共 {total_tasks} 个未完成任务：\n"]

    for item in overdue:
        lines.append(f"📄 {item['date']}.md（{item['days_ago']}天前）")
        for task in item["uncompleted"]:
            lines.append(f"   {task}")
        lines.append("")

    lines.append("💡 建议：运行 inherit_tasks 将未完成项带到今天。")
    return "\n".join(lines)


@mcp.tool()
def generate_review(date: str = "", write: bool = True) -> str:
    """生成指定日期的日终回顾（完成率 + 时间统计 + 明日建议）。

    Args:
        date: 日期，格式 YYYY-MM-DD。留空则默认今天。
        write: 是否写入 Daily 文件。默认 True。
    """
    today = datetime.strptime(date, "%Y-%m-%d") if date else datetime.now()
    today_str = today.strftime("%Y-%m-%d")
    today_file = DAILY_DIR / f"{today_str}.md"

    if not today_file.exists():
        return f"⚠️ 今日待办文件不存在: {today_str}.md"

    content = today_file.read_text(encoding="utf-8")
    completed, uncompleted = parse_all_tasks(content)

    total = len(completed) + len(uncompleted)
    if total == 0:
        return "📝 今日没有任何任务记录。"

    review = _generate_review_text(completed, uncompleted, today_str)

    if write:
        marker = "## 📊 日终回顾（自动生成"
        if marker in content:
            parts = content.split(marker)
            before = parts[0].rstrip()
            new_content = before + "\n\n" + review + "\n"
        else:
            manual_marker = "## 📊 日终回顾"
            if manual_marker in content:
                idx = content.index(manual_marker)
                before = content[:idx].rstrip()
                new_content = before + "\n\n" + review + "\n"
            else:
                new_content = content.rstrip() + "\n\n" + review + "\n"

        today_file.write_text(new_content, encoding="utf-8")
        return f"{review}\n\n✅ 回顾已写入 Daily/{today_str}.md"

    return review


@mcp.tool()
def scan_split(date: str = "") -> str:
    """检测今日 Daily 文件中需要拆分的任务。

    检测规则：
    - 预估时间 > 80min → 建议拆分
    - 没有预估时间标记 → 建议补上

    Args:
        date: 日期，格式 YYYY-MM-DD。留空则默认今天。
    """
    today = datetime.strptime(date, "%Y-%m-%d") if date else datetime.now()
    today_str = today.strftime("%Y-%m-%d")

    issues = scan_split_needed(DAILY_DIR, today)

    if not issues:
        return f"✅ {today_str} 的所有任务预估时间合理，无需拆分。"

    too_long = [i for i in issues if i["type"] == "too_long"]
    no_est = [i for i in issues if i["type"] == "no_estimate"]

    lines = []
    if too_long:
        lines.append(f"✂️ 以下 {len(too_long)} 个任务超过 80min，建议拆分：")
        for item in too_long:
            lines.append(f"  ⚠️ 『{item['description']}』— {item['minutes']}min")
        lines.append("")

    if no_est:
        lines.append(f"📝 以下 {len(no_est)} 个任务缺少预估时间：")
        for item in no_est:
            lines.append(f"  ❓ 『{item['description']}』")
        lines.append("")

    lines.append("💡 建议让 AI 帮你拆分大任务为多个 ≤ 45min 的子任务。")
    return "\n".join(lines)


# ============================================================
# Resources
# ============================================================

@mcp.resource("daily://today")
def resource_today() -> str:
    """今日 Daily 待办文件的完整内容。"""
    today_str = datetime.now().strftime("%Y-%m-%d")
    today_file = DAILY_DIR / f"{today_str}.md"

    if not today_file.exists():
        return f"⚠️ 今日文件不存在: {today_str}.md"
    return today_file.read_text(encoding="utf-8")


@mcp.resource("daily://dashboard")
def resource_dashboard() -> str:
    """Dashboard 面板内容。"""
    if not DASHBOARD_FILE.exists():
        return "⚠️ Dashboard.md 不存在"
    return DASHBOARD_FILE.read_text(encoding="utf-8")


@mcp.resource("daily://history")
def resource_history() -> str:
    """最近 7 天的任务完成统计。"""
    today = datetime.now()
    lines = ["📊 最近 7 天任务完成统计\n"]
    lines.append("| 日期 | 完成 | 未完成 | 完成率 |")
    lines.append("|------|:----:|:------:|:------:|")

    for i in range(7):
        day = today - timedelta(days=i)
        day_str = day.strftime("%Y-%m-%d")
        day_file = DAILY_DIR / f"{day_str}.md"

        if not day_file.exists():
            lines.append(f"| {day_str} | — | — | 无文件 |")
            continue

        content = day_file.read_text(encoding="utf-8")
        completed, uncompleted = parse_all_tasks(content)
        total = len(completed) + len(uncompleted)

        if total == 0:
            lines.append(f"| {day_str} | 0 | 0 | 无任务 |")
        else:
            pct = round(len(completed) / total * 100)
            lines.append(f"| {day_str} | {len(completed)} | {len(uncompleted)} | {pct}% |")

    return "\n".join(lines)


# ============================================================
# 入口
# ============================================================

if __name__ == "__main__":
    mcp.run()
