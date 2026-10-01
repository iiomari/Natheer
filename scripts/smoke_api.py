"""Verify the installed library APIs the plan depends on.

Prints versions and real signatures, and runs a tiny fit/sample to check
SDV reproducibility. Uses only random toy numbers, no personal data.

    python scripts\smoke_api.py > docs\api_smoke_output.txt
"""
from __future__ import annotations

import importlib
import importlib.metadata as md
import inspect

import numpy as np
import pandas as pd

PACKAGES = [
    "sdv", "sdmetrics", "rdt", "copulas", "ctgan", "pandas", "numpy", "scipy",
    "scikit-learn", "streamlit", "transformers", "torch", "huggingface-hub",
    "PyYAML", "pytest", "hypothesis",
]

SIGNATURES = [
    "sdv.metadata:Metadata.detect_from_dataframes",
    "sdv.metadata:Metadata.load_from_dict",
    "sdv.metadata:Metadata.add_table",
    "sdv.metadata:Metadata.add_column",
    "sdv.metadata:Metadata.update_column",
    "sdv.metadata:Metadata.set_primary_key",
    "sdv.metadata:Metadata.add_relationship",
    "sdv.metadata:Metadata.validate",
    "sdv.metadata:Metadata.validate_data",
    "sdv.metadata:Metadata.to_dict",
    "sdv.single_table:GaussianCopulaSynthesizer.__init__",
    "sdv.single_table:GaussianCopulaSynthesizer.fit",
    "sdv.single_table:GaussianCopulaSynthesizer.sample",
    "sdv.single_table:GaussianCopulaSynthesizer.reset_sampling",
    "sdv.single_table:CTGANSynthesizer.__init__",
    "sdv.multi_table:HMASynthesizer.__init__",
    "sdv.multi_table:HMASynthesizer.fit",
    "sdv.multi_table:HMASynthesizer.sample",
    "sdv.evaluation.single_table:evaluate_quality",
    "sdv.evaluation.single_table:run_diagnostic",
    "sdv.evaluation.multi_table:evaluate_quality",
    "transformers:pipeline",
]

OPTIONAL_CLASSES = [
    "sdmetrics.single_table:DCRBaselineProtection",
    "sdmetrics.single_table:DCROverfittingProtection",
    "sdmetrics.single_table:NewRowSynthesis",
    "sdmetrics.single_column:KSComplement",
    "sdmetrics.single_column:TVComplement",
]


def resolve(path: str):
    module_name, attr_path = path.split(":")
    obj = importlib.import_module(module_name)
    for part in attr_path.split("."):
        obj = getattr(obj, part)
    return obj


def section(title: str) -> None:
    print(f"\n## {title}")


def main() -> None:
    section("Versions")
    for pkg in PACKAGES:
        try:
            print(f"{pkg}=={md.version(pkg)}")
        except md.PackageNotFoundError:
            print(f"{pkg}: NOT INSTALLED")

    section("Signatures")
    for path in SIGNATURES:
        try:
            print(f"{path}{inspect.signature(resolve(path))}")
        except Exception as e:  # report and continue: this is a probe
            print(f"{path}: UNAVAILABLE ({type(e).__name__})")

    section("Optional SDMetrics classes")
    for path in OPTIONAL_CLASSES:
        try:
            resolve(path)
            print(f"{path}: available")
        except Exception as e:
            print(f"{path}: UNAVAILABLE ({type(e).__name__})")

    section("GaussianCopula reproducibility")
    from sdv.metadata import Metadata
    from sdv.single_table import GaussianCopulaSynthesizer

    rng = np.random.default_rng(0)
    toy = pd.DataFrame({
        "row_id": np.arange(300),
        "x": rng.normal(size=300),
        "y": rng.integers(0, 5, size=300),
        "cat": rng.choice(["a", "b", "c"], size=300),
    })
    meta = Metadata.detect_from_dataframes({"toy": toy})
    print("detected metadata:", meta.to_dict())

    def fit_sample() -> tuple[pd.DataFrame, pd.DataFrame]:
        s = GaussianCopulaSynthesizer(meta)
        s.fit(toy)
        first = s.sample(50)
        s.reset_sampling()
        return first, s.sample(50)

    a1, a2 = fit_sample()
    b1, _ = fit_sample()
    print("same synthesizer, sample after reset_sampling identical:", a1.equals(a2))
    print("two independent fits, first sample identical:", a1.equals(b1))


if __name__ == "__main__":
    main()
