from pathlib import Path


def test_core_package_never_imports_streamlit():
    core_dir = Path(__file__).resolve().parents[1] / "versa" / "core"
    offenders = []
    for path in core_dir.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "streamlit" in text:
            offenders.append(str(path))
    assert offenders == [], f"streamlit referenced in core: {offenders}"
