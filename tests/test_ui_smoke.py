from pathlib import Path

from streamlit.testing.v1 import AppTest

APP_PATH = str(Path(__file__).resolve().parents[1] / "versa" / "ui" / "app.py")


def test_empty_state_shows_upload_prompt_with_no_exception():
    at = AppTest.from_file(APP_PATH)
    at.run(timeout=30)

    assert not at.exception
    assert any("Загрузите файл" in info.value for info in at.info)


def test_real_sample_renders_header_summary_and_grouped_warnings(sample_path):
    at = AppTest.from_file(APP_PATH)
    at.run(timeout=60)
    at.get("file_uploader")[0].upload(
        sample_path.name, sample_path.read_bytes(),
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    at.run(timeout=60)

    assert not at.exception
    assert at.header[0].value == '№943-ТУ "Казачий 1 оч. НС_Генподряд"'

    md = [m.value for m in at.markdown]
    assert any("Паушальные суммы" in m for m in md)
    assert any("Включено в другую позицию" in m for m in md)
    # the pct_col #DIV/0! noise must never resurface as a warning group
    assert not any("Ошибки формул" in m for m in md)


def test_rubles_toggle_switches_summary_line_formatting(sample_path):
    at = AppTest.from_file(APP_PATH)
    at.run(timeout=60)
    at.get("file_uploader")[0].upload(
        sample_path.name, sample_path.read_bytes(),
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    at.run(timeout=60)

    at.checkbox[0].check()
    at.run(timeout=60)

    assert not at.exception
    md = [m.value for m in at.markdown]
    assert any("₽" in m and "млн" not in m for m in md)


def test_invalid_file_shows_friendly_error_not_a_traceback():
    at = AppTest.from_file(APP_PATH)
    at.run(timeout=30)
    at.get("file_uploader")[0].upload(
        "not_a_workbook.xlsx", b"this is not a real xlsx file at all",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    at.run(timeout=30)

    assert not at.exception
    assert len(at.error) == 1
    assert "сводную таблицу" in at.error[0].value
