from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from .config import EXPORT_DIR, PREVIEW_MAX_ROWS


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(col).strip() for col in df.columns]
    return df


def _df_preview(df: pd.DataFrame) -> dict[str, Any]:
    sample = df.head(PREVIEW_MAX_ROWS).fillna("")
    rows = sample.values.tolist()
    return {
        "type": "table",
        "columns": [str(col) for col in sample.columns],
        "rows": rows,
    }


def _resolve_column(df: pd.DataFrame, field: str) -> str | None:
    if field in df.columns:
        return field
    lowered = {str(col).lower(): str(col) for col in df.columns}
    return lowered.get(field.lower())


def execute_parse_excel(state: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    uploaded_file = state.get("uploaded_file")
    if not uploaded_file:
        raise ValueError("File is not uploaded yet.")

    df = pd.read_excel(uploaded_file)
    df = _normalize_columns(df)
    preview = _df_preview(df)

    state["columns"] = [str(col) for col in df.columns]
    state["preview"] = preview

    return state, {
        "message": "Excel parsed successfully.",
        "preview": preview,
    }


def execute_aggregate(state: dict[str, Any], parameters: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    uploaded_file = state.get("uploaded_file")
    field = state.get("selected_field") or parameters.get("field")
    method = parameters.get("method", "sum")

    if not uploaded_file:
        raise ValueError("File is not uploaded yet.")
    if not field:
        raise ValueError("No field selected for aggregation.")
    if method != "sum":
        raise ValueError(f"Unsupported method: {method}")

    df = pd.read_excel(uploaded_file)
    df = _normalize_columns(df)
    resolved_field = _resolve_column(df, field)
    if not resolved_field:
        raise ValueError(f"Field '{field}' not found in columns: {list(df.columns)}")

    series = pd.to_numeric(df[resolved_field], errors="coerce").fillna(0.0)
    total = float(series.sum())
    result_preview = {
        "type": "table",
        "columns": [f"{resolved_field}_sum"],
        "rows": [[total]],
    }

    state["selected_field"] = resolved_field
    state["aggregate_result"] = {
        "field": resolved_field,
        "method": method,
        "value": total,
    }
    state["preview"] = result_preview

    return state, {
        "message": f"Aggregation complete for '{resolved_field}'.",
        "preview": result_preview,
        "result": state["aggregate_result"],
    }


def execute_export_excel(workflow_id: str, state: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    result = state.get("aggregate_result")
    if not result:
        raise ValueError("No aggregation result to export.")

    output_path = Path(EXPORT_DIR) / f"{workflow_id}_result.xlsx"
    export_df = pd.DataFrame(
        [
            {
                "field": result["field"],
                "method": result["method"],
                "value": result["value"],
            }
        ]
    )
    export_df.to_excel(output_path, index=False)

    state["exported_file"] = str(output_path)
    return state, {
        "message": "Result exported successfully.",
        "payload": {
            "export_file": output_path.name,
            "download_url": f"/task/download/{workflow_id}",
        },
    }
