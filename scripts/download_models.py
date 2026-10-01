"""One-time, setup-only model download. This is the ONLY network step.

Carries no data: it fetches public model weights into the local Hugging Face
cache. At runtime Nazeer forces HF_HUB_OFFLINE=1 (see nazeer/config.py).

    python scripts\download_models.py
"""
from __future__ import annotations

import os
from pathlib import Path

# The runtime package sets offline mode on import, so this script must not import nazeer.
os.environ["HF_HUB_OFFLINE"] = "0"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"

from huggingface_hub import snapshot_download  # noqa: E402

# Apache-2.0; trained on ANERcorp (MSA). Labels include B-PERS / I-PERS.
MODELS = {
    "CAMeL-Lab/bert-base-arabic-camelbert-msa-ner": "54e2905e7c756883b00877cd48ed710a304af0d1",
}


def main() -> None:
    for repo_id, revision in MODELS.items():
        path = Path(snapshot_download(repo_id=repo_id, revision=revision))
        # The snapshot folder name is the resolved commit hash; pin it in MODELS.
        print(f"{repo_id}: commit {path.name} -> {path}")


if __name__ == "__main__":
    main()
