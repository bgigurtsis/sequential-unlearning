"""Bound preparation memory without changing rows, filtering or token packing."""

import re
from collections import deque

from scripts.erasure_pilot_b_data import MixedSequences, RelationshipFilter, SourceTokens


def has_overlap(text: str, grams: set[tuple[str, ...]]) -> bool:
    """Match the original five-word intersection with a five-word working buffer.
    Why: the old implementation allocates a set and several word lists per document.
    If wrong: a changed overlap test admits evaluation wording into training.
    """
    window = deque(maxlen=5)
    for match in re.finditer(r"\w+", text.casefold()):
        window.append(match.group())
        if len(window) == 5 and tuple(window) in grams:
            return True
    return False


class BoundedFilter(RelationshipFilter):
    """Keep the November classifier and thresholds with bounded overlap storage.
    Why: an allocation fix must not change which documents the filter accepts.
    If wrong: different training text confounds the student comparison.
    """

    def reason(self, text: str) -> str | None:
        """Copy the November filter, replacing only the overlap allocation.
        Why: keyword priority, window order and embedding batches must stay identical.
        If wrong: different document decisions change the frozen data mixture.
        """
        if not text.strip():
            return "empty"
        if self.keywords.search(text):
            return "keyword"
        if has_overlap(text, self.collision_grams):
            return "development_overlap"
        width, stride = self.spec["window_characters"], self.spec["window_stride"]
        for start in range(0, len(text), stride * 128):
            windows = [text[offset:offset + width] for offset in
                       range(start, min(start + stride * 128, len(text)), stride)]
            scores = self.classifier.predict_proba(self.embed(windows))
            if any(float(score[1]) >= self.spec["probability_threshold"] for score in scores):
                return "embedding"
        return None


def live_stream(spec: dict, tokenizer) -> MixedSequences:
    """Read small Arrow batches with no file prebuffer or expanding byte cache.
    Why: datasets 5.1 defaults to whole-row-group batches and Arrow prebuffering.
    If wrong: multiple suspended source readers can exhaust preparation host RAM.
    """
    from datasets import load_dataset
    from pyarrow.dataset import ParquetFragmentScanOptions

    relationship_filter = BoundedFilter(spec["filter"])
    sources = []
    options = ParquetFragmentScanOptions(pre_buffer=False, use_buffered_stream=True,
                                         buffer_size=1024 * 1024)
    for source in spec["datasets"]:
        columns = ["messages"] if source["format"] == "messages" else ["text"]
        if source["name"] == "wikipedia":
            columns.append("title")
        rows = load_dataset(source["id"], name=source["subset"], split=source["split"],
                            revision=source["revision"], streaming=True, batch_size=128,
                            columns=columns, fragment_scan_options=options,
                            storage_options={"cache_type": "none"})
        rows = rows.shuffle(seed=spec["seed"], buffer_size=source["shuffle_buffer"])
        sources.append(SourceTokens(rows, source, tokenizer, relationship_filter))
    return MixedSequences(sources, [source["tokens"] for source in spec["datasets"]],
                          spec["sequence_length"])
