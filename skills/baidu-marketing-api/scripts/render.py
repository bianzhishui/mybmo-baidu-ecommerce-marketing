"""输出渲染：默认 JSON（便于上游程序解析），可选 Markdown 表格（便于人直接看）。"""

from __future__ import annotations

import json

MAX_ROWS = 60
MAX_COLS = 9


def emit(data, fmt="json", *, title=""):
    if fmt == "md":
        print(to_markdown(data, title=title))
    else:
        print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def to_markdown(data, *, title=""):
    lines = []
    if title:
        lines.append(f"**{title}**")
        lines.append("")

    if isinstance(data, dict) and isinstance(data.get("words"), list):
        meta = {k: v for k, v in data.items() if k != "words"}
        if meta:
            lines.append("```json")
            lines.append(json.dumps(meta, ensure_ascii=False, indent=2, default=str))
            lines.append("```")
            lines.append("")
        lines.append(_table(data["words"]))
        return "\n".join(lines)

    if isinstance(data, list) and data and isinstance(data[0], dict):
        lines.append(_table(data))
        return "\n".join(lines)

    lines.append("```json")
    lines.append(json.dumps(data, ensure_ascii=False, indent=2, default=str))
    lines.append("```")
    return "\n".join(lines)


def _table(rows):
    if not rows:
        return "_无数据_"
    cols = list(rows[0].keys())[:MAX_COLS]
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for row in rows[:MAX_ROWS]:
        cells = [_cell(row.get(c)) for c in cols]
        out.append("| " + " | ".join(cells) + " |")
    if len(rows) > MAX_ROWS:
        out.append("")
        out.append(f"_共 {len(rows)} 行，仅显示前 {MAX_ROWS} 行，完整数据请用 --format json_")
    return "\n".join(out)


def _cell(value):
    if value is None:
        return "-"
    if isinstance(value, (list, dict)):
        text = json.dumps(value, ensure_ascii=False)
    else:
        text = str(value)
    return text.replace("|", "\\|").replace("\n", " ")
