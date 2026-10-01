"""CamelBERT Arabic NER (CAMeL-Lab/bert-base-arabic-camelbert-msa-ner, Apache-2.0).

Loaded ONLY from the local Hugging Face cache (runtime is offline; the weights are
fetched once by scripts/download_models.py). Person entities (PERS) become name spans.
If the model is missing or a batch run exceeds its time budget, the remaining texts
fall back to the gazetteer and `stats` records what happened.
"""
from __future__ import annotations

import logging
import time

from nazeer.ner import GazetteerNER, NERUnavailable

log = logging.getLogger(__name__)

MODEL_ID = "CAMeL-Lab/bert-base-arabic-camelbert-msa-ner"
PERSON_LABELS = {"PERS", "PER", "PERSON"}


class CamelNER:
    name = "camelbert"

    def __init__(self, nlp, min_score: float = 0.5, time_budget_s: float = 900.0, batch_size: int = 16):
        self._nlp = nlp
        self.min_score = min_score
        self.time_budget_s = time_budget_s
        self.batch_size = batch_size
        self._fallback = GazetteerNER()
        self.stats = {"model": MODEL_ID, "texts_model": 0, "texts_fallback": 0, "fallback_reason": None}

    @classmethod
    def load(cls, **kwargs) -> "CamelNER":
        try:
            from huggingface_hub import snapshot_download
            from transformers import pipeline

            path = snapshot_download(MODEL_ID, local_files_only=True)
            nlp = pipeline("token-classification", model=path, tokenizer=path, aggregation_strategy="simple",
                           device=-1)
        except Exception as e:  # noqa: BLE001
            raise NERUnavailable(f"CamelBERT not available locally ({type(e).__name__}); "
                                 "run scripts\\download_models.py once") from None
        return cls(nlp, **kwargs)

    def _spans(self, entities) -> list[tuple[int, int, float]]:
        out = []
        for e in entities:
            if e.get("entity_group") in PERSON_LABELS and float(e.get("score", 0)) >= self.min_score:
                start, end = int(e["start"]), int(e["end"])
                if end > start:
                    out.append((start, end, round(float(e["score"]), 3)))
        return out

    def find(self, text: str) -> list[tuple[int, int, float]]:
        return self.find_many([text])[0]

    def find_many(self, texts: list[str]) -> list[list[tuple[int, int, float]]]:
        results: list[list[tuple[int, int, float]]] = []
        t0 = time.perf_counter()
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i:i + self.batch_size]
            if time.perf_counter() - t0 > self.time_budget_s:
                self.stats["fallback_reason"] = f"time budget of {self.time_budget_s:.0f}s exceeded"
                for text in texts[i:]:
                    results.append(self._fallback.find(text))
                    self.stats["texts_fallback"] += 1
                log.warning("CamelBERT time budget exceeded; %d texts used the gazetteer", len(texts) - i)
                break
            try:
                outputs = self._nlp(batch, batch_size=self.batch_size)
            except Exception:  # noqa: BLE001 - model failure: gazetteer for this batch
                log.warning("CamelBERT batch failed; gazetteer used for %d texts", len(batch), exc_info=True)
                self.stats["fallback_reason"] = "model error on a batch"
                results += [self._fallback.find(t) for t in batch]
                self.stats["texts_fallback"] += len(batch)
                continue
            results += [self._spans(o) for o in outputs]
            self.stats["texts_model"] += len(batch)
        return results


class UnionNER:
    """CamelBERT spans plus gazetteer spans (overlaps merged, longest kept)."""
    name = "camelbert+gazetteer"

    def __init__(self, camel: CamelNER):
        self.camel, self.gazetteer = camel, GazetteerNER()
        self.stats = camel.stats

    @staticmethod
    def _merge(a: list[tuple[int, int, float]], b: list[tuple[int, int, float]]) -> list[tuple[int, int, float]]:
        spans = sorted(a + b, key=lambda x: (x[0], -(x[1] - x[0])))
        out: list[tuple[int, int, float]] = []
        for s in spans:
            if out and s[0] < out[-1][1]:
                prev = out[-1]
                out[-1] = (prev[0], max(prev[1], s[1]), max(prev[2], s[2]))
            else:
                out.append(s)
        return out

    def find(self, text: str) -> list[tuple[int, int, float]]:
        return self.find_many([text])[0]

    def find_many(self, texts: list[str]) -> list[list[tuple[int, int, float]]]:
        camel = self.camel.find_many(texts)
        return [self._merge(c, self.gazetteer.find(t)) for c, t in zip(camel, texts)]
