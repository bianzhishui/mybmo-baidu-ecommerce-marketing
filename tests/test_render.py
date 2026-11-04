"""输出渲染：JSON 兜底 + Markdown 表格，以及截断与转义。"""

import json

import render


def test_list_of_dicts_becomes_table():
    rows = [{"word": "月季", "pv": 1200}, {"word": "玫瑰花", "pv": 800}]

    md = render.to_markdown(rows)

    assert "| word | pv |" in md
    assert "| 月季 | 1200 |" in md


def test_words_payload_splits_meta_and_table():
    payload = {"total": 2, "query": "月季", "words": [{"word": "月季", "pv": 1200}]}

    md = render.to_markdown(payload, title="拓词结果")

    assert md.startswith("**拓词结果**")
    assert '"total": 2' in md, "元信息应单独渲染成 JSON 块"
    assert "| word | pv |" in md
    assert "| 月季 | 1200 |" in md


def test_scalar_falls_back_to_json_block():
    md = render.to_markdown("ok")

    assert md.startswith("```json")
    assert json.loads(md.split("```")[1].removeprefix("json")) == "ok"


def test_empty_table_is_explicit():
    assert render._table([]) == "_无数据_"


def test_table_truncates_with_hint():
    rows = [{"i": i} for i in range(render.MAX_ROWS + 1)]

    md = render._table(rows)

    assert f"共 {render.MAX_ROWS + 1} 行" in md
    assert f"前 {render.MAX_ROWS} 行" in md


def test_table_limits_columns():
    row = {f"c{i}": i for i in range(render.MAX_COLS + 3)}

    header = render._table([row]).splitlines()[0]

    assert header.count("|") == render.MAX_COLS + 1


def test_cell_escapes_pipe_and_newline():
    assert render._cell(None) == "-"
    assert render._cell("a|b") == "a\\|b"
    assert render._cell("a\nb") == "a b"
    assert render._cell({"k": 1}) == '{"k": 1}'


def test_emit_writes_json_by_default(capsys):
    render.emit({"a": 1})

    assert json.loads(capsys.readouterr().out) == {"a": 1}


def test_emit_markdown(capsys):
    render.emit([{"a": 1}], fmt="md")

    assert "| a |" in capsys.readouterr().out
