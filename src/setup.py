"""
日常小助手 MCP Server — 首次初始化脚本

运行后自动完成：
1. 创建数据目录（Daily/ + Dashboard.md）
2. 生成 config.json（路径适配当前 OS）
3. 打印 .mcp.json 配置模板 + 安装指令

支持 Windows / macOS / Linux。

用法:
    Windows:  py setup.py
    macOS:    python3 setup.py
"""

import json
import platform
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()


def detect_python_cmd() -> str:
    """检测当前 OS 的 Python 命令。"""
    if platform.system() == "Windows":
        return "py"
    return "python3"


def prompt_data_dir() -> Path:
    """询问用户数据目录位置。"""
    default = Path.home() / "Desktop" / "日常小助手"
    print(f"\n📁 数据目录将存放 Daily 文件、Dashboard 等。")
    print(f"   默认位置: {default}")
    user_input = input(f"\n   按 Enter 使用默认，或输入自定义路径: ").strip()

    if user_input:
        return Path(user_input).resolve()
    return default


def create_data_dir(data_dir: Path) -> None:
    """创建数据目录结构。"""
    daily_dir = data_dir / "Daily"
    daily_dir.mkdir(parents=True, exist_ok=True)
    print(f"   ✅ 创建: {daily_dir}")

    # Dashboard.md
    dashboard = data_dir / "Dashboard.md"
    if not dashboard.exists():
        dashboard.write_text(
            "# 📊 日常小助手 Dashboard\n\n"
            "> 全局任务概览面板\n\n"
            "## 🔴 超期任务\n\n"
            "> 由 `check_overdue` 工具自动检测\n\n"
            "## 🟡 今日待办\n\n"
            "> 由 `get_today` 工具读取\n\n"
            "## 🟢 已完成\n\n"
            "> 由 `generate_review` 工具统计\n\n"
            "---\n\n"
            "*Dashboard 由日常小助手 MCP Server 提供数据支持*\n",
            encoding="utf-8",
        )
        print(f"   ✅ 创建: {dashboard}")
    else:
        print(f"   ⏭️  已存在: {dashboard}")


def create_config(data_dir: Path) -> None:
    """生成 config.json。"""
    config_path = SCRIPT_DIR / "config.json"
    config = {
        "daily_dir": str(data_dir / "Daily"),
        "dashboard_file": str(data_dir / "Dashboard.md"),
    }

    config_path.write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"   ✅ 生成: {config_path}")


def print_next_steps(data_dir: Path) -> None:
    """打印后续步骤。"""
    python_cmd = detect_python_cmd()
    server_path = SCRIPT_DIR / "server.py"

    # 根据 OS 格式化路径
    if platform.system() == "Windows":
        server_path_str = str(server_path).replace("/", "\\")
        path_escaped = json.dumps(server_path_str)  # 自动转义反斜杠
    else:
        server_path_str = str(server_path)
        path_escaped = json.dumps(server_path_str)

    mcp_json = {
        "mcpServers": {
            "daily-assistant": {
                "command": python_cmd,
                "args": ["-X", "utf8", server_path_str],
            }
        }
    }
    mcp_json_str = json.dumps(mcp_json, ensure_ascii=False, indent=2)

    print(f"\n{'='*50}")
    print(f"🎉 初始化完成！接下来：")
    print(f"{'='*50}")

    print(f"\n📦 步骤 1: 安装 fastmcp")
    print(f"   {python_cmd} -m pip install fastmcp")

    print(f"\n📝 步骤 2: 配置 Claude Code")
    print(f"   在你的项目根目录创建 .mcp.json，内容如下：")
    print(f"\n{mcp_json_str}")

    print(f"\n🚀 步骤 3: 启动 Claude Code")
    print(f"   在包含 .mcp.json 的目录下启动 claude")
    print(f"   MCP Server 会自动加载，输入 /mcp 确认")

    print(f"\n📅 步骤 4: 创建今日待办")
    print(f"   在 Claude Code 中说: \"用 inherit_tasks 创建今天的待办\"")
    print(f"   或手动在 {data_dir / 'Daily'} 中创建 YYYY-MM-DD.md 文件")

    print(f"\n💡 任务格式:")
    print(f"   - [ ] 任务描述 ⏱️45min 📅 2026-03-30 ⏫")
    print(f"   标记: ⏱️=预估时间 📅=deadline ⏫=最高优先 🔼=高 🔽=低")


def main():
    print("=" * 50)
    print("🛠️  日常小助手 MCP Server — 初始化向导")
    print("=" * 50)
    print(f"\n   系统: {platform.system()} {platform.release()}")
    print(f"   Python: {sys.version.split()[0]}")
    print(f"   脚本目录: {SCRIPT_DIR}")

    # 1. 数据目录
    data_dir = prompt_data_dir()
    print(f"\n📂 创建数据目录...")
    create_data_dir(data_dir)

    # 2. config.json
    print(f"\n⚙️  生成配置文件...")
    create_config(data_dir)

    # 3. 后续步骤
    print_next_steps(data_dir)


if __name__ == "__main__":
    main()
