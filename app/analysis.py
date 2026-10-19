"""Turn an uploaded training-log JSON into a full DERMS-R analysis payload.

All scoring/statistics are delegated to the `dermsr` package (derms_score,
normalize, rank_matrix, friedman_test, nemenyi_critical_difference,
critical_pairs) -- nothing here redefines the metric or the statistical
tests, it only shapes data in and out of them.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from dermsr import derms_score, normalize
from dermsr.statistics import critical_pairs, friedman_test, nemenyi_critical_difference, rank_matrix

# Accepts this project's own benchmark-CSV naming (combined_summary.csv,
# from the derms-r repo) as well as dermsr's own canonical column names, so
# a real export from either pipeline works without renaming.
_ALIASES = {
    "architecture": ["architecture", "model", "arch"],
    "dataset_ratio": ["dataset_ratio", "ratio", "data_ratio"],
    "n_parameters": ["n_parameters", "num_parameters", "parameters", "trainable_parameters"],
    "mean_val_accuracy": ["mean_val_accuracy", "mean_validation_accuracy"],
    "std_val_accuracy": ["std_val_accuracy", "sd_validation_accuracy"],
}

_RADAR_AXES = ["Accuracy", "Compactness", "Stability", "Data Efficiency"]


class AnalysisError(ValueError):
    """Raised for malformed uploads; the caller turns this into a 400."""


def _first_present(row: dict, keys: list[str]) -> Any:
    for k in keys:
        if k in row and row[k] is not None:
            return row[k]
    return None


def _fold_columns(row: dict) -> list[float]:
    folds = []
    i = 1
    while f"fold_{i}_accuracy" in row:
        if row[f"fold_{i}_accuracy"] is not None:
            folds.append(float(row[f"fold_{i}_accuracy"]))
        i += 1
    return folds


def normalize_records(records: list[dict]) -> pd.DataFrame:
    """Map arbitrary input column names onto dermsr's canonical schema."""
    if not records:
        raise AnalysisError("Uploaded file contains no rows.")

    rows = []
    for i, raw in enumerate(records):
        architecture = _first_present(raw, _ALIASES["architecture"])
        dataset_ratio = _first_present(raw, _ALIASES["dataset_ratio"])
        n_parameters = _first_present(raw, _ALIASES["n_parameters"])
        mean_acc = _first_present(raw, _ALIASES["mean_val_accuracy"])
        std_acc = _first_present(raw, _ALIASES["std_val_accuracy"])

        if architecture is None or dataset_ratio is None or n_parameters is None:
            raise AnalysisError(
                f"Row {i}: missing one of architecture/dataset_ratio/n_parameters "
                f"(got keys: {sorted(raw.keys())})."
            )

        if mean_acc is None or std_acc is None:
            folds = _fold_columns(raw)
            if len(folds) < 2:
                raise AnalysisError(
                    f"Row {i} ({architecture}, ratio={dataset_ratio}): need either "
                    "mean_val_accuracy+std_val_accuracy, or >=2 fold_N_accuracy columns."
                )
            mean_acc = float(np.mean(folds))
            std_acc = float(np.std(folds, ddof=1))

        rows.append(
            {
                "architecture": str(architecture),
                "dataset_ratio": float(dataset_ratio),
                "n_parameters": float(n_parameters),
                "mean_val_accuracy": float(mean_acc),
                "std_val_accuracy": float(std_acc),
            }
        )

    df = pd.DataFrame(rows)
    dupes = df.duplicated(subset=["architecture", "dataset_ratio"], keep=False)
    if dupes.any():
        offending = df.loc[dupes, ["architecture", "dataset_ratio"]].drop_duplicates()
        raise AnalysisError(
            "Duplicate (architecture, dataset_ratio) rows found -- aggregate to one row per "
            f"pair before uploading: {offending.to_dict('records')}"
        )
    return df


def _score_table(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    result = derms_score(
        mean_val_accuracy=out["mean_val_accuracy"].to_numpy(),
        dataset_ratio=out["dataset_ratio"].to_numpy(),
        n_parameters=out["n_parameters"].to_numpy(),
        std_val_accuracy=out["std_val_accuracy"].to_numpy(),
        return_components=True,
    )
    out["performance"] = result.performance
    out["data_efficiency"] = result.data_efficiency
    out["complexity_efficiency"] = result.complexity_efficiency
    out["stability"] = result.stability
    out["derms_r_raw"] = result.score
    out["derms_r_normalized"] = normalize(out["derms_r_raw"].to_numpy())
    return out


def _optimal_points(scored: pd.DataFrame) -> pd.DataFrame:
    idx = scored.groupby("architecture")["derms_r_raw"].idxmax()
    optimal = scored.loc[idx].reset_index(drop=True).rename(columns={"dataset_ratio": "optimal_ratio"})
    optimal["derms_r_normalized"] = normalize(optimal["derms_r_raw"].to_numpy())
    return optimal.sort_values("derms_r_raw", ascending=False).reset_index(drop=True)


def _radar_axes(optimal: pd.DataFrame) -> list[dict]:
    """Min-max scale 4 axes across the uploaded architectures, inverted where
    a smaller raw value is more favorable (parameters, std dev, ratio), so a
    larger axis value is always more DERMS-R-favorable -- same convention as
    the paper's appendix radar figure.
    """

    def mm(series: pd.Series, invert: bool) -> pd.Series:
        lo, hi = series.min(), series.max()
        if hi == lo:
            scaled = pd.Series(1.0, index=series.index)
        else:
            scaled = (series - lo) / (hi - lo)
        return 1 - scaled if invert else scaled

    acc = mm(optimal["mean_val_accuracy"], invert=False)
    compact = mm(optimal["n_parameters"], invert=True)
    stability = mm(optimal["std_val_accuracy"], invert=True)
    data_eff = mm(optimal["optimal_ratio"], invert=True)

    panels = []
    for i, row in optimal.iterrows():
        panels.append(
            {
                "architecture": row["architecture"],
                "values": [float(acc[i]), float(compact[i]), float(stability[i]), float(data_eff[i])],
            }
        )
    return panels


def _statistics(scored: pd.DataFrame) -> dict:
    n_arch = scored["architecture"].nunique()
    n_ratios = scored["dataset_ratio"].nunique()
    if n_arch < 2 or n_ratios < 2:
        return {
            "available": False,
            "reason": (
                f"Need at least 2 architectures and 2 dataset ratios for the Friedman/Nemenyi "
                f"analysis (got {n_arch} architecture(s), {n_ratios} ratio(s))."
            ),
        }
    if not (2 <= n_arch <= 20):
        return {
            "available": False,
            "reason": f"Nemenyi critical difference is only tabulated for 2-20 architectures (got {n_arch}).",
        }

    ranks = rank_matrix(scored, block_col="dataset_ratio", treatment_col="architecture", value_col="derms_r_raw")
    friedman = friedman_test(ranks)
    cd = nemenyi_critical_difference(k=friedman.k, n=friedman.n)
    pairs = critical_pairs(friedman.average_ranks, cd)

    return {
        "available": True,
        "chi2_f": friedman.chi2_f,
        "df": friedman.df,
        "k": friedman.k,
        "n": friedman.n,
        "f_f": friedman.f_f,
        "f_df1": friedman.f_df1,
        "f_df2": friedman.f_df2,
        "p_value": friedman.p_value,
        "average_ranks": [
            {"architecture": a, "average_rank": float(r)} for a, r in friedman.average_ranks.items()
        ],
        "critical_difference": cd,
        "critical_pairs": pairs.to_dict("records"),
    }


def run_analysis(records: list[dict]) -> dict:
    df = normalize_records(records)
    scored = _score_table(df)
    optimal = _optimal_points(scored)

    return {
        "rows": scored.sort_values(["architecture", "dataset_ratio"]).to_dict("records"),
        "optimal": optimal.to_dict("records"),
        "radar": {"axes": _RADAR_AXES, "panels": _radar_axes(optimal)},
        "statistics": _statistics(scored),
    }
