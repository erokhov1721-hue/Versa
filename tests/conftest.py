from pathlib import Path

import pytest

SAMPLE_PATH = (
    Path(__file__).resolve().parents[1]
    / "samples"
    / "943-ТУ__Сводная_Казачий_НС_-_фасады_и_ВИС.xlsx"
)


@pytest.fixture(scope="session")
def sample_path() -> Path:
    assert SAMPLE_PATH.exists(), f"missing sample file: {SAMPLE_PATH}"
    return SAMPLE_PATH


@pytest.fixture(scope="session")
def sample_tender(sample_path):
    from versa.core.parser import parse_tender

    return parse_tender(sample_path)
