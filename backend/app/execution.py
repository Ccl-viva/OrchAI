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


def _uploaded_extension(uploaded_file: str) -> str:
    return Path(uploaded_file).suffix.lower()


def _read_uploaded_dataframe(
    *,
    uploaded_file: str,
    sheet_name: str | int | None = None,
    delimiter: str | None = None,
) -> pd.DataFrame:
    extension = _uploaded_extension(uploaded_file)
    if extension == ".csv":
        sep = delimiter if isinstance(delimiter, str) and delimiter else ","
        return pd.read_csv(uploaded_file, sep=sep)
    if extension == ".tsv":
        sep = delimiter if isinstance(delimiter, str) and delimiter else "\t"
        return pd.read_csv(uploaded_file, sep=sep)
    read_kwargs: dict[str, Any] = {}
    if isinstance(sheet_name, (str, int)):
        read_kwargs["sheet_name"] = sheet_name
    return pd.read_excel(uploaded_file, **read_kwargs)


def execute_parse_excel(
    state: dict[str, Any],
    parameters: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    uploaded_file = state.get("uploaded_file")
    if not uploaded_file:
        raise ValueError("File is not uploaded yet.")

    parameters = parameters or {}
    sheet_name = parameters.get("sheet_name", state.get("parse_sheet"))
    df = _read_uploaded_dataframe(uploaded_file=uploaded_file, sheet_name=sheet_name)
    df = _normalize_columns(df)
    preview = _df_preview(df)

    state["columns"] = [str(col) for col in df.columns]
    state["preview"] = preview
    if isinstance(sheet_name, (str, int)):
        state["parse_sheet"] = sheet_name

    return state, {
        "message": "Excel parsed successfully." if not isinstance(sheet_name, (str, int)) else f"Excel parsed from sheet '{sheet_name}'.",
        "preview": preview,
    }


def execute_parse_csv(
    state: dict[str, Any],
    parameters: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    uploaded_file = state.get("uploaded_file")
    if not uploaded_file:
        raise ValueError("File is not uploaded yet.")
    extension = _uploaded_extension(uploaded_file)
    if extension not in {".csv", ".tsv"}:
        raise ValueError("Uploaded file is not a CSV/TSV file.")

    parameters = parameters or {}
    delimiter = parameters.get("delimiter", state.get("parse_delimiter"))
    if not isinstance(delimiter, str) or not delimiter:
        delimiter = "\t" if extension == ".tsv" else ","

    df = _read_uploaded_dataframe(uploaded_file=uploaded_file, delimiter=delimiter)
    df = _normalize_columns(df)
    preview = _df_preview(df)

    state["columns"] = [str(col) for col in df.columns]
    state["preview"] = preview
    state["parse_delimiter"] = delimiter

    return state, {
        "message": f"CSV parsed successfully (delimiter '{delimiter}').",
        "preview": preview,
    }


def _normalize_method(method: str | None) -> str:
    raw = (method or "sum").strip().lower()
    if raw in {"", "none", "null"}:
        return "sum"
    if raw in {"avg", "average"}:
        return "mean"
    return raw


def _apply_aggregation(series: pd.Series, method: str) -> float:
    if method == "sum":
        return float(series.sum())
    if method == "mean":
        return float(series.mean()) if len(series) else 0.0
    if method == "max":
        return float(series.max()) if len(series) else 0.0
    if method == "min":
        return float(series.min()) if len(series) else 0.0
    if method == "count":
        return float(series.count())
    raise ValueError(f"Unsupported method: {method}")


def execute_aggregate(state: dict[str, Any], parameters: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    uploaded_file = state.get("uploaded_file")
    field = state.get("selected_field") or parameters.get("field")
    method_source = state.get("selected_method") or parameters.get("method") or "sum"
    method = _normalize_method(str(method_source))

    if not uploaded_file:
        raise ValueError("File is not uploaded yet.")
    if not field:
        raise ValueError("No field selected for aggregation.")
    extension = _uploaded_extension(uploaded_file)
    sheet_name = state.get("parse_sheet")
    delimiter = state.get("parse_delimiter")
    if extension in {".csv", ".tsv"}:
        df = _read_uploaded_dataframe(uploaded_file=uploaded_file, delimiter=delimiter if isinstance(delimiter, str) else None)
    else:
        df = _read_uploaded_dataframe(uploaded_file=uploaded_file, sheet_name=sheet_name if isinstance(sheet_name, (str, int)) else None)
    df = _normalize_columns(df)
    resolved_field = _resolve_column(df, field)
    if not resolved_field:
        raise ValueError(f"Field '{field}' not found in columns: {list(df.columns)}")

    series = pd.to_numeric(df[resolved_field], errors="coerce").fillna(0.0)
    total = _apply_aggregation(series, method)
    result_preview = {
        "type": "table",
        "columns": [f"{resolved_field}_{method}"],
        "rows": [[total]],
    }

    state["selected_field"] = resolved_field
    state["selected_method"] = method
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


def execute_export_excel(
    workflow_id: str,
    state: dict[str, Any],
    parameters: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    result = state.get("aggregate_result")
    if not result:
        raise ValueError("No aggregation result to export.")

    parameters = parameters or {}
    export_name = str(parameters.get("export_name") or state.get("export_name") or "").strip()
    if export_name and not export_name.lower().endswith(".xlsx"):
        export_name = f"{export_name}.xlsx"
    if not export_name:
        export_name = f"{workflow_id}_result.xlsx"
    output_path = Path(EXPORT_DIR) / export_name
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
    state["export_name"] = export_name
    return state, {
        "message": "Result exported successfully.",
        "payload": {
            "export_file": output_path.name,
            "download_url": f"/task/download/{workflow_id}",
        },
    }


def execute_export_csv(
    workflow_id: str,
    state: dict[str, Any],
    parameters: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    result = state.get("aggregate_result")
    if not result:
        raise ValueError("No aggregation result to export.")

    parameters = parameters or {}
    export_name = str(parameters.get("export_name") or state.get("export_name") or "").strip()
    if export_name and not export_name.lower().endswith(".csv"):
        export_name = f"{export_name}.csv"
    if not export_name:
        export_name = f"{workflow_id}_result.csv"

    output_path = Path(EXPORT_DIR) / export_name
    export_df = pd.DataFrame(
        [
            {
                "field": result["field"],
                "method": result["method"],
                "value": result["value"],
            }
        ]
    )
    export_df.to_csv(output_path, index=False)

    state["exported_file"] = str(output_path)
    state["export_name"] = export_name
    return state, {
        "message": "Result exported successfully.",
        "payload": {
            "export_file": output_path.name,
            "download_url": f"/task/download/{workflow_id}",
        },
    }
