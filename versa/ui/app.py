from __future__ import annotations

import io

import streamlit as st

from versa.core.compare import compare_section, compare_tender
from versa.core.models import ComparisonMode
from versa.core.parser import parse_tender
from versa.ui.charts import deviation_heatmap, waterfall_by_section, waterfall_diff
from versa.ui.formatting import to_millions, to_rubles

st.set_page_config(page_title="Versa — сравнение КП", layout="wide")
st.title("Versa — сравнение коммерческих предложений")

uploaded = st.file_uploader("Загрузите сводную таблицу (.xlsx)", type=["xlsx"])
if uploaded is None:
    st.info("Загрузите файл, чтобы увидеть сравнение.")
    st.stop()


@st.cache_data(show_spinner="Разбираю сводную таблицу...")
def _parse_cached(file_bytes: bytes):
    return parse_tender(io.BytesIO(file_bytes))


try:
    tender = _parse_cached(uploaded.getvalue())
except Exception as exc:
    st.error(
        "Не получилось прочитать файл как сводную таблицу тендера. "
        f"Проверьте, что это тот самый шаблон (лист «3_ ПОДРОБНАЯ»). Ошибка: {exc}"
    )
    st.stop()

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

if tender.mode == ComparisonMode.BASELINE:
    mode_choice = st.radio(
        "Режим сравнения", options=["Авто (А)", "А", "Б"], horizontal=True,
        help="Расчётная стоимость заполнена — режим А доступен.",
    )
    effective_mode = ComparisonMode.PEER if mode_choice == "Б" else ComparisonMode.BASELINE
else:
    st.caption(
        "Режим сравнения: Б (участники между собой) — расчётная стоимость "
        "в файле не заполнена, режим А недоступен для этого тендера."
    )
    effective_mode = ComparisonMode.PEER

show_rubles = st.checkbox("Показывать полные рубли вместо млн ₽")


def _fmt(value: float | None) -> str:
    return f"{to_rubles(value)} ₽" if show_rubles else f"{to_millions(value)} млн ₽"


st.markdown("### Итоги по участникам (за объёмы заказчика)")
totals = comparison["totals_by_customer_volume"]
ranked = sorted(totals.items(), key=lambda kv: kv[1])
best = ranked[0][1] if ranked else None
for pid, value in ranked:
    name = tender.participant_by_id(pid).name
    deviation = f"+{(value - best) / best * 100:.1f}% от лучшего" if best else ""
    st.write(f"{name}: **{_fmt(value)}** {deviation}")

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
            f"<div style='{style}'>{tender.participant_by_id(pid).name}<br>{_fmt(value)}</div>",
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
WARNING_GROUP_LABELS = {
    "lump_sum": "Паушальные суммы (весь раздел одной строкой)",
    "included_elsewhere": "Включено в другую позицию",
    "volume_mismatch": "Расхождение объёмов с заказчиком",
    "placeholder": "Заглушки (символическая цена)",
    "not_included": "Не включено",
    "formula_error": "Ошибки формул в исходном файле",
}
WARNING_GROUP_ORDER = [
    "lump_sum", "included_elsewhere", "volume_mismatch",
    "placeholder", "not_included", "formula_error",
]

if not tender.warnings:
    st.success("Предупреждений нет")
else:
    by_type: dict[str, list] = {}
    for warning in tender.warnings:
        by_type.setdefault(warning.type.value, []).append(warning)

    for type_key in WARNING_GROUP_ORDER:
        items = by_type.pop(type_key, [])
        if not items:
            continue
        st.markdown(f"**{WARNING_GROUP_LABELS.get(type_key, type_key)} ({len(items)})**")
        shown = items[:50]
        for warning in shown:
            participant_name = (
                tender.participant_by_id(warning.participant_id).name
                if warning.participant_id else "—"
            )
            st.warning(f"строка {warning.row}, {participant_name}: {warning.message}")
        if len(items) > len(shown):
            st.caption(f"и ещё {len(items) - len(shown)}")

    for type_key, items in by_type.items():
        st.markdown(f"**{type_key} ({len(items)})**")
