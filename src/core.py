"""
日常小助手 MCP Server — 核心逻辑模块

从 5 个源脚本中提取的纯函数，零外部依赖（仅标准库）。
所有函数接受 daily_dir: Path 参数，不硬编码任何路径。

来源映射：
  - next_action.py   → parse_task, rank_tasks, generate_steps, format_*
  - overdue_check.py  → scan_overdue_files
  - daily_inherit.py  → find_latest_daily, extract_uncompleted_tasks, create_today_file
  - daily_review.py   → parse_all_tasks, generate_review
  - action_notify.py  → scan_split_needed
"""

import re
from datetime import datetime, timedelta
from pathlib import Path


# ============================================================
# 常量
# ============================================================

PRIORITY_WEIGHT = {
    "highest": 40,  # ⏫
    "high": 30,     # 🔼
    "medium": 20,   # （无标记）
    "low": 10,      # 🔽
}

PRIORITY_MAP = {
    "⏫": "highest",
    "🔼": "high",
    "🔽": "low",
}

PRIORITY_LABEL = {
    "highest": "最高 ⏫",
    "high": "高 🔼",
    "medium": "普通",
    "low": "低 🔽",
}

WEEKDAY_MAP = {
    0: "周一", 1: "周二", 2: "周三", 3: "周四",
    4: "周五", 5: "周六", 6: "周日",
}


# ============================================================
# 任务解析与排序（来源: next_action.py）
# ============================================================

def parse_task(line: str, today: datetime = None) -> dict | None:
    """
    解析一行任务文本，提取描述、预估时间、deadline、优先级。
    只处理未完成任务（- [ ] 开头）。
    """
    today = today or datetime.now()
    stripped = line.strip()

    if not stripped.startswith("- [ ] "):
        return None

    raw_text = stripped[6:]

    # 提取预估时间 ⏱️XXmin
    time_match = re.search(r"⏱️\s*(\d+)\s*min", raw_text)
    est_minutes = int(time_match.group(1)) if time_match else None

    # 提取 deadline 📅 YYYY-MM-DD
    deadline_match = re.search(r"📅\s*(\d{4}-\d{2}-\d{2})", raw_text)
    deadline = None
    days_until = None
    if deadline_match:
        deadline = deadline_match.group(1)
        deadline_date = datetime.strptime(deadline, "%Y-%m-%d").date()
        today_date = today.date() if hasattr(today, "date") else today
        days_until = (deadline_date - today_date).days

    # 提取优先级 ⏫ 🔼 🔽
    priority = "medium"
    for emoji, level in PRIORITY_MAP.items():
        if emoji in raw_text:
            priority = level
            break

    # 清理描述文本
    desc = raw_text
    desc = re.sub(r"\s*⏱️\s*\d+\s*min", "", desc)
    desc = re.sub(r"\s*📅\s*\d{4}-\d{2}-\d{2}", "", desc)
    for emoji in PRIORITY_MAP:
        desc = desc.replace(emoji, "")
    desc = desc.replace("🔄", "").strip()

    return {
        "raw": stripped,
        "description": desc,
        "est_minutes": est_minutes,
        "deadline": deadline,
        "days_until": days_until,
        "priority": priority,
    }


def rank_tasks(tasks: list[dict]) -> list[dict]:
    """按优先级和 deadline 紧迫度排序。第一个 = 最应该做的。"""

    def sort_key(task):
        priority_score = PRIORITY_WEIGHT.get(task["priority"], 20)
        deadline_score = 0
        if task["days_until"] is not None:
            if task["days_until"] < 0:
                deadline_score = 100 + abs(task["days_until"])
            elif task["days_until"] == 0:
                deadline_score = 80
            elif task["days_until"] <= 1:
                deadline_score = 60
            elif task["days_until"] <= 3:
                deadline_score = 40
            elif task["days_until"] <= 7:
                deadline_score = 20
            else:
                deadline_score = 10
        return -(priority_score + deadline_score)

    return sorted(tasks, key=sort_key)


def generate_steps(task: dict) -> list[str]:
    """基于任务描述生成建议步骤（简单关键词匹配）。"""
    desc = task["description"]

    if any(kw in desc for kw in ["写", "撰写", "完成"]):
        return ["打开相关文档/笔记", "花 5 分钟回顾之前的进展和大纲", "开始写作，先不追求完美"]
    elif any(kw in desc for kw in ["收集", "找", "搜索", "查"]):
        return ["明确搜索关键词和范围", "在目标平台上系统搜索", "整理结果到笔记中"]
    elif any(kw in desc for kw in ["整理", "归类", "分类", "梳理"]):
        return ["打开所有相关材料", "定义分类维度", "逐项归类并记录"]
    elif any(kw in desc for kw in ["回复", "发送", "邮件", "联系"]):
        return ["打开相关沟通工具", "组织要表达的要点", "发送并记录"]
    elif any(kw in desc for kw in ["读", "阅读", "看", "学习"]):
        return ["找到要阅读的材料", "带着问题阅读，标注重点", "写下 3 个关键要点"]
    else:
        return ["明确完成标准", "执行第一个小步骤", "完成后检查是否达标"]


def format_deadline_label(days_until: int | None, deadline: str | None) -> str:
    """格式化 deadline 显示。"""
    if days_until is None or deadline is None:
        return "无 deadline"
    if days_until < 0:
        return f"{deadline}（已超期 {abs(days_until)} 天！）"
    elif days_until == 0:
        return f"{deadline}（今天！）"
    elif days_until == 1:
        return f"{deadline}（明天）"
    else:
        return f"{deadline}（{days_until} 天后）"


def format_recommendation(tasks: list[dict], today: datetime = None) -> str:
    """格式化推荐输出。"""
    today = today or datetime.now()

    if not tasks:
        return "🎉 今日任务清零！\n所有任务都已完成，干得漂亮！"

    top = tasks[0]
    time_label = f"预计 {top['est_minutes']}min" if top["est_minutes"] else "未设定时间"
    deadline_label = format_deadline_label(top["days_until"], top["deadline"])
    priority_label = PRIORITY_LABEL.get(top["priority"], "普通")
    steps = generate_steps(top)

    lines = [
        "",
        f"🎯 现在做这个（{time_label}）：",
        f"{top['description']}",
        "",
        f"📅 Deadline: {deadline_label}",
        f"🔥 优先级: {priority_label}",
        "",
        "💡 建议步骤：",
    ]
    for i, step in enumerate(steps, 1):
        lines.append(f"  {i}. {step}")

    if len(tasks) > 1:
        nxt = tasks[1]
        nxt_time = f"（{nxt['est_minutes']}min）" if nxt["est_minutes"] else ""
        lines.extend(["", "⏭️ 做完之后：", f"  → {nxt['description']}{nxt_time}"])

    remaining = len(tasks)
    total_minutes = sum(t["est_minutes"] for t in tasks if t["est_minutes"])
    lines.append("")
    lines.append(f"📊 剩余 {remaining} 个任务" + (f"，共约 {total_minutes}min" if total_minutes else ""))

    return "\n".join(lines)


# ============================================================
# 超期检测（来源: overdue_check.py）
# ============================================================

def scan_overdue_files(daily_dir: Path, today: datetime = None) -> list[dict]:
    """
    扫描 Daily 文件夹，找出所有超期文件。
    超期 = 文件日期 < 今天 且 包含未完成任务。
    """
    today = today or datetime.now()
    today_str = today.strftime("%Y-%m-%d")
    date_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}\.md$")

    overdue = []
    for f in sorted(daily_dir.iterdir()):
        if not f.is_file() or not date_pattern.match(f.name):
            continue
        file_date = f.stem
        if file_date >= today_str:
            continue

        content = f.read_text(encoding="utf-8")
        uncompleted = [
            line.strip()
            for line in content.split("\n")
            if line.strip().startswith("- [ ] ")
        ]

        if uncompleted:
            file_dt = datetime.strptime(file_date, "%Y-%m-%d")
            days_ago = (today - file_dt).days
            overdue.append({
                "file": f,
                "date": file_date,
                "days_ago": days_ago,
                "uncompleted": uncompleted,
            })

    overdue.sort(key=lambda x: x["date"], reverse=True)
    return overdue


# ============================================================
# 待办继承（来源: daily_inherit.py）
# ============================================================

def find_latest_daily(daily_dir: Path, before_date: datetime = None) -> Path | None:
    """在 Daily 文件夹中找到日期最新的待办文件（before_date 之前）。"""
    date_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}\.md$")
    today_str = (before_date or datetime.now()).strftime("%Y-%m-%d")

    candidates = [
        f for f in daily_dir.iterdir()
        if f.is_file() and date_pattern.match(f.name) and f.stem < today_str
    ]

    if not candidates:
        return None

    candidates.sort(key=lambda f: f.name, reverse=True)
    return candidates[0]


def extract_uncompleted_tasks(file_path: Path) -> list[str]:
    """从待办文件中提取所有未完成的任务行。"""
    content = file_path.read_text(encoding="utf-8")
    return [
        line.strip()
        for line in content.split("\n")
        if line.strip().startswith("- [ ] ")
    ]


def create_today_file(
    daily_dir: Path,
    today: datetime,
    inherited_tasks: list[str],
    source_date: str = None,
) -> Path:
    """创建今天的待办文件。"""
    date_str = today.strftime("%Y-%m-%d")
    weekday = WEEKDAY_MAP[today.weekday()]
    file_path = daily_dir / f"{date_str}.md"

    yaml_lines = ["---", f"title: 每日待办 - {date_str}", f"date: {date_str}"]
    if source_date:
        yaml_lines.append(f"inherited_from: {source_date}")
    yaml_lines.append("---")

    body_lines = ["", f"# 📅 {date_str} {weekday} 每日待办", "", "## 📥 今日任务", ""]

    if inherited_tasks:
        for task in inherited_tasks:
            task_text = task[6:]  # 去掉 "- [ ] "
            task_text = task_text.replace(" 🔄", "").replace("🔄", "").rstrip()
            body_lines.append(f"- [ ] {task_text} 🔄")
        body_lines.append("")

    body_lines.extend([
        "", "## 📝 备注", "", "", "",
        "## 📊 日终回顾", "",
        "> *下班前填写*",
        "> - 完成了什么？",
        "> - 没完成什么？为什么？",
        "> - 明天最重要的事是？",
    ])

    content = "\n".join(yaml_lines) + "\n" + "\n".join(body_lines) + "\n"
    file_path.write_text(content, encoding="utf-8")
    return file_path


def mark_tasks_inherited(file_path: Path, target_date: str) -> int:
    """将源文件中的未完成任务标记为已继承。

    - [ ] 任务  →  - [>] 任务 ➡️ YYYY-MM-DD

    已标记 [>] 的任务不会被 check_overdue / recommend_next 等函数匹配，
    从而避免继承后的重复计数。

    返回标记的任务数量。
    """
    content = file_path.read_text(encoding="utf-8")
    lines = content.split("\n")
    count = 0

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("- [ ] "):
            # 保留原始缩进
            indent = line[: len(line) - len(line.lstrip())]
            task_text = stripped[6:]
            lines[i] = f"{indent}- [>] {task_text} ➡️ {target_date}"
            count += 1

    if count > 0:
        file_path.write_text("\n".join(lines), encoding="utf-8")

    return count


# ============================================================
# 日终回顾（来源: daily_review.py）
# ============================================================

def parse_all_tasks(content: str) -> tuple[list[dict], list[dict]]:
    """解析 Daily 文件中的所有任务（已完成 + 未完成）。"""
    completed = []
    uncompleted = []

    for line in content.split("\n"):
        stripped = line.strip()
        is_done = stripped.startswith("- [x] ")
        is_todo = stripped.startswith("- [ ] ")

        if not is_done and not is_todo:
            continue

        raw_text = stripped[6:]

        time_match = re.search(r"⏱️\s*(\d+)\s*min", raw_text)
        est_minutes = int(time_match.group(1)) if time_match else None

        desc = raw_text
        desc = re.sub(r"\s*⏱️\s*\d+\s*min", "", desc)
        desc = re.sub(r"\s*📅\s*\d{4}-\d{2}-\d{2}", "", desc)
        desc = re.sub(r"\s*✅\s*\d{4}-\d{2}-\d{2}", "", desc)
        for emoji in ["⏫", "🔼", "🔽", "🔄"]:
            desc = desc.replace(emoji, "")
        desc = desc.strip()

        task = {"description": desc, "est_minutes": est_minutes}
        if is_done:
            completed.append(task)
        else:
            uncompleted.append(task)

    return completed, uncompleted


def generate_review(
    completed: list[dict], uncompleted: list[dict], today_str: str
) -> str:
    """生成日终回顾 markdown 内容。"""
    total = len(completed) + len(uncompleted)
    pct = round(len(completed) / total * 100) if total > 0 else 0

    completed_min = sum(t["est_minutes"] for t in completed if t["est_minutes"])
    uncompleted_min = sum(t["est_minutes"] for t in uncompleted if t["est_minutes"])

    lines = [
        f"## 📊 日终回顾（自动生成 {today_str}）",
        "",
        f"**📈 完成率：** {len(completed)}/{total}（{pct}%）",
        "",
    ]

    if completed:
        lines.append("**✅ 已完成：**")
        for t in completed:
            time_str = f"（{t['est_minutes']}min）" if t["est_minutes"] else ""
            lines.append(f"- {t['description']}{time_str}")
        lines.append("")

    if uncompleted:
        lines.append("**⬜ 未完成：**")
        for t in uncompleted:
            time_str = f"（{t['est_minutes']}min）" if t["est_minutes"] else ""
            lines.append(f"- {t['description']}{time_str}")
        lines.append("")

    lines.extend([
        "**⏱️ 时间统计：**",
        f"- 已完成预估总时间：{completed_min}min",
        f"- 未完成预估总时间：{uncompleted_min}min",
        "",
    ])

    if uncompleted:
        lines.append("**💡 明日建议：**")
        lines.append(f"- {len(uncompleted)} 个未完成任务将被继承到明天")
        if uncompleted_min > 0:
            lines.append(f"- 预计需要 {uncompleted_min}min 完成剩余任务")
    else:
        lines.append("**💡 明日建议：**")
        lines.append("- 今天全部完成！明天可以开始新的任务 🎉")

    return "\n".join(lines)


# ============================================================
# 拆分检测（来源: action_notify.py）
# ============================================================

def scan_split_needed(daily_dir: Path, today: datetime) -> list[dict]:
    """
    检测今日 Daily 文件中需要拆分的任务。
    规则：⏱️ > 80min → 建议拆分；无 ⏱️ → 建议补上。
    """
    today_str = today.strftime("%Y-%m-%d")
    today_file = daily_dir / f"{today_str}.md"

    if not today_file.exists():
        return []

    content = today_file.read_text(encoding="utf-8")
    issues = []

    for line in content.split("\n"):
        stripped = line.strip()
        if not stripped.startswith("- [ ] "):
            continue

        raw_text = stripped[6:]
        time_match = re.search(r"⏱️\s*(\d+)\s*min", raw_text)

        desc = raw_text
        desc = re.sub(r"\s*⏱️\s*\d+\s*min", "", desc)
        desc = re.sub(r"\s*📅\s*\d{4}-\d{2}-\d{2}", "", desc)
        for emoji in ["⏫", "🔼", "🔽", "🔄"]:
            desc = desc.replace(emoji, "")
        desc = desc.strip()

        if time_match:
            minutes = int(time_match.group(1))
            if minutes > 80:
                issues.append({"description": desc, "minutes": minutes, "type": "too_long"})
        else:
            issues.append({"description": desc, "minutes": None, "type": "no_estimate"})

    return issues
