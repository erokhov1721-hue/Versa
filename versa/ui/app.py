from __future__ import annotations

import tempfile
from pathlib import Path

import streamlit as st

from versa.core.compare import compare_section, compare_tender
from versa.core.models import ComparisonMode
from versa.core.parser import parse_tender
from versa.ui.charts import deviation_heatmap, waterfall_by_section, waterfall_diff
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

participant_ids = [p.id for p in tender.participants]

st.markdown("### Разделы")
for section in tender.sections:
    result = compare_section(section, participant_ids, effective_mode)
    cols = st.columns(len(participant_ids) + 1)
    cols[0].write(f"**{section.number}. {section.title}**")
    for i, pid in enumerate(participant_ids, start=1):
        value = result.values.get(pid, 0.0)
        is_min = result.min is not None and value == result.min
        is_max = result.max is not None and value == result.max
        style = "background-color: #d4f7d4" if is_min else ("background-color: #f7d4d4" if is_max else "")
        cols[i].markdown(
            f"<div style='{style}'>{tender.participant_by_id(pid).name}<br>{to_millions(value)}</div>",
            unsafe_allow_html=True,
        )

st.markdown("### Водопад по разделам")
selected_participant = st.selectbox("Участник", options=participant_ids,
                                     format_func=lambda pid: tender.participant_by_id(pid).name)
st.plotly_chart(waterfall_by_section(tender, selected_participant), width='stretch')

st.markdown("### Разница между двумя участниками")
col_a, col_b = st.columns(2)
participant_a = col_a.selectbox("Участник A", options=participant_ids,
                                 format_func=lambda pid: tender.participant_by_id(pid).name, key="pa")
participant_b = col_b.selectbox("Участник Б", options=participant_ids,
                                 format_func=lambda pid: tender.participant_by_id(pid).name, key="pb")
st.plotly_chart(waterfall_diff(tender, participant_a, participant_b), width='stretch')

st.markdown("### Тепловая карта отклонений от медианы")
st.plotly_chart(deviation_heatmap(tender, participant_ids), width='stretch')

st.markdown("### Предупреждения")
if not tender.warnings:
    st.success("Предупреждений нет")
for warning in tender.warnings[:200]:
    participant_name = (
        tender.participant_by_id(warning.participant_id).name
        if warning.participant_id else "—"
    )
    st.warning(f"[{warning.type.value}] строка {warning.row}, {participant_name}: {warning.message}")
