from __future__ import annotations

import plotly.graph_objects as go

from versa.core.aggregate import section_totals
from versa.core.models import Tender


def _top_level_section_values(tender: Tender, participant_id: str) -> dict[str, float]:
    return {
        section.number: section_totals(section).by_customer_volume.get(participant_id, 0.0)
        for section in tender.sections
    }


def waterfall_by_section(tender: Tender, participant_id: str) -> go.Figure:
    values = _top_level_section_values(tender, participant_id)
    labels = list(values.keys()) + ["Итого"]
    measures = ["relative"] * len(values) + ["total"]
    amounts = list(values.values()) + [sum(values.values())]
    fig = go.Figure(go.Waterfall(x=labels, measure=measures, y=amounts))
    fig.update_layout(title=f"Состав итога: {participant_id}")
    return fig


def waterfall_diff(tender: Tender, participant_a: str, participant_b: str) -> go.Figure:
    values_a = _top_level_section_values(tender, participant_a)
    values_b = _top_level_section_values(tender, participant_b)
    labels = list(values_a.keys()) + ["Итого"]
    diffs = [values_a[k] - values_b[k] for k in values_a]
    diffs.append(sum(diffs))
    fig = go.Figure(go.Waterfall(
        x=labels, measure=["relative"] * (len(labels) - 1) + ["total"], y=diffs
    ))
    fig.update_layout(title=f"Разница по разделам: {participant_a} − {participant_b}")
    return fig


def deviation_heatmap(tender: Tender, participant_ids: list[str]) -> go.Figure:
    section_numbers = [s.number for s in tender.sections]
    z = []
    for pid in participant_ids:
        row = []
        for section in tender.sections:
            totals = section_totals(section).by_customer_volume
            values = [totals.get(p, 0.0) for p in participant_ids if totals.get(p, 0.0)]
            median = sorted(values)[len(values) // 2] if values else 0.0
            value = totals.get(pid, 0.0)
            pct = ((value - median) / median * 100) if median else 0.0
            row.append(pct)
        z.append(row)
    fig = go.Figure(go.Heatmap(z=z, x=section_numbers, y=participant_ids, colorscale="RdYlGn_r"))
    fig.update_layout(title="Отклонение от медианы по разделам, %")
    return fig
