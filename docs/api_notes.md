# API notes (verified against installed versions)

Verified 2026-09-30 on Python 3.11.9 / Windows 11 with the versions in
`requirements.txt`. Raw probe output: `docs/api_smoke_output.txt`, which comes
from `scripts/smoke_api.py`. Re-run it after any version bump.

## Environment

- The global Python site has pandas 3.0.0 and torch 2.2.2. SDV/SDMetrics require
  `pandas<3` and transformers 5.x requires `torch>=2.5`, so **always use `.venv`**.
- `pip check` is clean. The full resolved set is in `requirements-lock.txt`.

## SDV 1.38.5

### Metadata
- `Metadata.detect_from_dataframes(data, infer_sdtypes=True, infer_keys='primary_and_foreign', foreign_key_inference_algorithm='column_name_match', verbose=False)`
  - FK inference only matches column names. Our `profiling.py` infers FKs by
    value containment plus name similarity, and builds the SDV metadata itself via
    `Metadata.load_from_dict(metadata_dict, single_table_name=None)`.
- Dict format (from `to_dict()`):
  ```python
  {"tables": {"toy": {"columns": {"row_id": {"sdtype": "id"}, "x": {"sdtype": "numerical"}},
                      "primary_key": "row_id"}},
   "relationships": [],
   "METADATA_SPEC_VERSION": "V1"}
  ```
- A small-cardinality integer column (5 distinct values) was auto-detected as
  `categorical`, not `numerical`. We set sdtypes explicitly.
- `add_relationship(parent_table_name, child_table_name, parent_primary_key, child_foreign_key)`,
  `set_primary_key(column_name, table_name=None)`,
  `update_column(column_name, table_name=None, **kwargs)`, `validate()`, `validate_data(data)`.

### Single table
- `GaussianCopulaSynthesizer(metadata, enforce_min_max_values=True, enforce_rounding=True, locales=['en_US'], numerical_distributions=None, default_distribution=None)`
- `fit(data)`, `sample(num_rows, max_tries_per_batch=100, batch_size=None, output_file_path=None)`, `reset_sampling()`
- **There is no seed parameter, and sampling is deterministic:**
  - After `reset_sampling()`, the same fitted synthesizer gives identical samples.
  - Two independent fits on the same data gave identical first samples.
  - So SDV seeds itself internally. Implication for `synth.Synthesizer`: the SDV
    adapter cannot honor an arbitrary `seed`. Runs are reproducible by default,
    and the report states "seed: fixed by SDV".
- `CTGANSynthesizer(..., epochs=300, enable_gpu=True, batch_size=500, ...)`. Training is
  slow on CPU, so the demo uses fewer epochs if CTGAN is used at all.
- Fitting warns "We strongly recommend saving the metadata using 'save_to_json'".
  This is harmless, and we do not persist metadata.

### Multi table
- `HMASynthesizer(metadata, locales=['en_US'], verbose=True)`, `fit(data: dict)`, `sample(scale=1.0)`.
  There is no `num_rows`; size is set by `scale`. The docs say it is optimized for about
  5 tables and depth 1.

### Evaluation
- Use `sdv.evaluation.evaluate_quality(real_data, synthetic_data, metadata, verbose=True)`
  and `sdv.evaluation.run_diagnostic(real_data, synthetic_data, metadata, constraints=None, verbose=True)`.
  Importing via `sdv.evaluation.single_table` emits a FutureWarning.

## SDMetrics 0.32.0
- Available: `KSComplement`, `TVComplement`, `NewRowSynthesis`, `DCRBaselineProtection`, `DCROverfittingProtection`.
- `DCROverfittingProtection.compute_breakdown(real_training_data, synthetic_data, real_validation_data, metadata, table_name, num_rows_subsample=None, num_iterations=1)`
  matches our holdout design. We use it as a cross-check next to our own rule
  (median DCR twin→train ≥ median DCR holdout→train, plus the "closer to train" share).
- `DCRBaselineProtection.compute_breakdown(real_data, synthetic_data, metadata, table_name, num_rows_subsample=None, num_iterations=1)`.

## transformers 5.17.0
- `pipeline(task, model, ..., revision=None, device=None, dtype='auto', trust_remote_code=None, model_kwargs=None, **kwargs)`.
  For NER, `aggregation_strategy` goes through `**kwargs`. Verify it at M8 with the local model snapshot.

## Network and telemetry audit
- **sdv, sdmetrics, rdt, copulas, ctgan:** the only network code is `sdv/datasets/demo.py`
  (boto3 download of SDV's public demo datasets). Nazeer never calls it.
- **SDV logging:** `sdv/logging/utils.py` copies `sdv_logger_config.yml` into
  `platformdirs.user_data_dir('sdv', 'sdv-dev')` (a config file, no data). The default is
  `log_registry: null`, so no log file is written, and records propagate to our filtered
  root handlers. Records contain only event, class name, synthesizer id, and row/column
  counts. A user-level config could enable a CSV `FileHandler` with `propagate: false`, so
  the SDV adapter must call `nazeer.safe_log.route_library_loggers()` after constructing a
  synthesizer.
- **Streamlit 1.63:** `.streamlit/config.toml` sets `gatherUsageStats = false`,
  `address = "localhost"` and `showErrorDetails = "type"`. Streamlit still **prints full
  exception messages to its console**, so `app.py` must catch errors itself and log them
  through `safe_log`.
- **Hugging Face:** `import nazeer` forces `HF_HUB_OFFLINE`, `TRANSFORMERS_OFFLINE` and
  `HF_HUB_DISABLE_TELEMETRY`. Only `scripts/download_models.py` goes online, and it does not
  import `nazeer`.

## Licenses (from installed package metadata)
| Package | License |
|---|---|
| sdv, ctgan, copulas, rdt, deepecho | **BUSL-1.1** |
| sdmetrics, Faker | MIT |
| transformers, streamlit, boto3 | Apache-2.0 |
| torch | Apache-2.0 plus bundled permissive licenses |
| CAMeL-Lab/bert-base-arabic-camelbert-msa-ner | Apache-2.0 (model card) |

BUSL-1.1 Additional Use Grant: use is allowed except "for a Synthetic Data Service". The change
to MIT happens 4 years after each release. **copulas and rdt are BUSL too**, so a future
replacement behind the `Synthesizer` protocol must use scipy/numpy directly, not copulas or rdt.
