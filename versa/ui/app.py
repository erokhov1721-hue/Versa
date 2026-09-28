from __future__ import annotations

import tempfile
from pathlib import Path

import streamlit as st

from versa.core.compare import compare_tender
from versa.core.models import ComparisonMode
from versa.core.parser import parse_tender
from versa.ui.formatting import to_millions

st.set_page_config(page_title="Versa — сравнение КП", layout="wide")
st.title("Versa — сравнение коммерческих предложений")

uploaded = st.file_uploader("Загрузите сводную таблицу (.xlsx)", type=["xlsx"])
if uploaded is None:
    st.info("Загрузите файл, чтобы увидеть сравнение.")
    st.stop()

with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
    tmp.write(uploaded.getbuffer())
    tmp_path = Path(tmp.name)

tender = parse_tender(tmp_path)
comparison = compare_tender(tender)

st.header(tender.subject)
st.subheader(tender.object_name)
st.caption(tender.address)

st.markdown("### Участники")
for participant in tender.participants:
    st.write(
        f"**{participant.name}** · ИНН {participant.inn or '—'} · "
        f"{participant.accreditation_status or 'статус не указан'}"
    )

mode_label = "А (сравнение с расчётной стоимостью)" if tender.mode == ComparisonMode.BASELINE else "Б (сравнение участников между собой)"
mode_choice = st.radio(
    "Режим сравнения", options=["Авто", "А", "Б"], horizontal=True,
    help=f"Определён автоматически: режим {mode_label}",
)
effective_mode = tender.mode if mode_choice == "Авто" else (
    ComparisonMode.BASELINE if mode_choice == "А" else ComparisonMode.PEER
)

st.markdown("### Итоги по участникам (за объёмы заказчика)")
totals = comparison["totals_by_customer_volume"]
ranked = sorted(totals.items(), key=lambda kv: kv[1])
best = ranked[0][1] if ranked else None
for pid, value in ranked:
    name = tender.participant_by_id(pid).name
    deviation = f"+{(value - best) / best * 100:.1f}% от лучшего" if best else ""
    st.write(f"{name}: **{to_millions(value)} млн ₽** {deviation}")

st.markdown("### Предупреждения")
if not tender.warnings:
    st.success("Предупреждений нет")
for warning in tender.warnings[:200]:
    participant_name = (
        tender.participant_by_id(warning.participant_id).name
        if warning.participant_id else "—"
    )
    st.warning(f"[{warning.type.value}] строка {warning.row}, {participant_name}: {warning.message}")
