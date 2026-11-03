"""Stream the fixed B mixture and exclude relationship documents before packing."""

import hashlib
import json
import re
from collections import Counter, deque
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/erasure_pilot_v1/approach_b/settings.json"


def read_settings() -> dict:
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def word_ngrams(text: str, size: int = 5) -> set[tuple[str, ...]]:
    words = re.findall(r"\w+", text.casefold())
    return set(zip(*(words[index:] for index in range(size))))


def development_ngrams() -> set[tuple[str, ...]]:
    """Collect visible evaluation wording without opening the sealed set.
    Why: streamed retain text must not teach the development questions.
    If wrong: evaluation wording can enter training and overstate retention.
    """
    grams = set()
    for name in ("development.json", "nearby.json", "distant.json"):
        payload = json.loads((CONFIG.parent.parent / name).read_text(encoding="utf-8"))
        for item in payload["items"]:
            for turn in item["turns"]:
                grams.update(word_ngrams(turn))
    return grams


def document_text(row: dict, source: dict, tokenizer) -> str:
    """Render complete source documents, including both sides of instruction chat.
    Why: a relationship answer can follow an apparently unrelated prompt.
    If wrong: filtering only the prompt admits target knowledge in answers.
    """
    if source["format"] == "messages":
        messages = row.get("messages", [])
        if not messages or any(message.get("role") not in {"user", "assistant"} for message in messages):
            return ""  # Unsupported roles are excluded, never silently changed into user text.
        return tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=False)
    title = row.get("title", "")
    return (title + "\n" + row.get("text", "")).strip()


class RelationshipFilter:
    """Apply word-boundary keywords and a small embedding classifier to whole documents."""

    def __init__(self, spec: dict, embed=None, classifier=None, collision_grams=None):
        """Load only the filter dependencies needed by an actual data stream.
        Why: offline tests must use injected CPU functions without downloads.
        If wrong: preparation can make network requests or skip semantic filtering.
        """
        self.spec = spec
        escaped = [re.escape(word).replace(r"\ ", r"\s+") for word in spec["keywords"]]
        self.keywords = re.compile(r"(?<!\w)(?:" + "|".join(escaped) + r")(?!\w)", re.IGNORECASE)
        self.collision_grams = development_ngrams() if collision_grams is None else collision_grams
        if embed is None:
            from sentence_transformers import SentenceTransformer
            encoder = SentenceTransformer(spec["embedding_model"], revision=spec["embedding_revision"], device="cuda")
            encoder.max_seq_length = 256
            embed = lambda texts: encoder.encode(texts, batch_size=256, normalize_embeddings=True,
                                                 show_progress_bar=False, convert_to_numpy=True)
        self.embed = embed
        if classifier is None:
            from sklearn.linear_model import LogisticRegression
            examples = spec["positive_examples"] + spec["negative_examples"]
            labels = [1] * len(spec["positive_examples"]) + [0] * len(spec["negative_examples"])
            classifier = LogisticRegression(C=10.0, class_weight="balanced", random_state=20261101, max_iter=1000)
            classifier.fit(self.embed(examples), labels)
        self.classifier = classifier

    def reason(self, text: str) -> str | None:
        """Reject any document with a keyword, visible test overlap or semantic hit.
        Why: checking every short window avoids encoder truncation hiding later content.
        If wrong: retained documents can reintroduce the concept during distillation.
        """
        if not text.strip():
            return "empty"
        if self.keywords.search(text):
            return "keyword"
        if self.collision_grams.intersection(word_ngrams(text)):
            return "development_overlap"
        # Small character windows remain below MiniLM's 256 wordpiece limit in ordinary English.
        width, stride = self.spec["window_characters"], self.spec["window_stride"]
        for start in range(0, len(text), stride * 128):
            windows = [text[offset:offset + width] for offset in
                       range(start, min(start + stride * 128, len(text)), stride)]
            scores = self.classifier.predict_proba(self.embed(windows))
            if any(float(score[1]) >= self.spec["probability_threshold"] for score in scores):
                return "embedding"
        return None


class SourceTokens:
    """Read each source once and retain removal counts plus a digest of accepted text."""

    def __init__(self, rows, source: dict, tokenizer, relationship_filter):
        """Keep one source's iterator, token buffer and removal counters together.
        Why: the stream must account for documents it removes before packing tokens.
        If wrong: source quotas or removal shares can be attributed to another corpus.
        """
        self.rows = iter(rows)
        self.source = source
        self.tokenizer = tokenizer
        self.filter = relationship_filter
        self.pending = deque()
        self.stats = Counter()
        self.digest = hashlib.sha256()

    def take(self, count: int) -> list[int]:
        """Return accepted tokens without resetting an exhausted source.
        Why: silent cycling changes the dataset and repeats training material.
        If wrong: the recorded mixture no longer identifies what the student saw.
        """
        output = []
        while len(output) < count:
            if not self.pending:
                try:
                    row = next(self.rows)
                except StopIteration:
                    raise RuntimeError(f"Source exhausted before its token quota: {self.source['id']}") from None
                text = document_text(row, self.source, self.tokenizer)
                self.stats["documents_seen"] += 1
                reason = self.filter.reason(text)
                if reason:
                    self.stats["documents_removed"] += 1
                    self.stats[reason] += 1
                    continue
                self.stats["documents_accepted"] += 1
                encoded = self.tokenizer.encode(text, add_special_tokens=False)
                # Natural documents end with EOS. Chat already ends with Gemma's turn boundary.
                if not encoded or encoded[-1] not in {1, 106}:
                    encoded.append(1)
                self.pending.extend(encoded)
                self.digest.update(text.encode("utf-8") + b"\0")
            amount = min(count - len(output), len(self.pending))
            for _ in range(amount):
                output.append(self.pending.popleft())
        self.stats["tokens_emitted"] += len(output)
        return output

    def summary(self) -> dict:
        seen = self.stats["documents_seen"]
        return {**dict(self.stats), "accepted_text_sha256": self.digest.hexdigest(),
                "removed_document_share": self.stats["documents_removed"] / seen if seen else None}


class MixedSequences:
    """Pack a deterministic token mixture with exact per-source quotas."""

    def __init__(self, sources: list[SourceTokens], quotas: list[int], length: int = 1024):
        if len(sources) != len(quotas) or any(quota <= 0 for quota in quotas):
            raise ValueError("Each source needs a positive token quota")
        self.sources = sources
        self.quotas = quotas
        self.length = length
        self.used = [0] * len(sources)

    def __iter__(self):
        """Yield fixed-width sequences and a mask for the final partial sequence.
        Why: document-sampling probabilities do not give the fixed 35/35/30 token mix.
        If wrong: variable document lengths change both training dose and source shares.
        """
        while sum(self.used) < sum(self.quotas):
            tokens = []
            while len(tokens) < self.length:
                active = [index for index, quota in enumerate(self.quotas) if self.used[index] < quota]
                if not active:
                    break
                index = min(active, key=lambda item: self.used[item] / self.quotas[item])
                count = min(self.length - len(tokens), self.quotas[index] - self.used[index])
                tokens.extend(self.sources[index].take(count))
                self.used[index] += count
            valid = len(tokens)
            yield {"input_ids": tokens + [1] * (self.length - valid),
                   "attention_mask": [1] * valid + [0] * (self.length - valid), "tokens": valid}

    def summary(self) -> dict:
        return {source.source["name"]: {"quota": quota, **source.summary()}
                for source, quota in zip(self.sources, self.quotas)}


def live_stream(settings: dict, tokenizer) -> MixedSequences:
    """Open pinned public datasets in streaming mode for the full planned run.
    Why: downloading entire web and Wikipedia corpora wastes the pod budget.
    If wrong: startup can consume the budget before the first optimiser step.
    """
    from datasets import load_dataset

    relationship_filter = RelationshipFilter(settings["filter"])
    sources = []
    for source in settings["datasets"]:
        rows = load_dataset(source["id"], name=source["subset"], split=source["split"],
                            revision=source["revision"], streaming=True)
        rows = rows.shuffle(seed=settings["seed"], buffer_size=source["shuffle_buffer"])
        sources.append(SourceTokens(rows, source, tokenizer, relationship_filter))
    return MixedSequences(sources, [source["tokens"] for source in settings["datasets"]], settings["sequence_length"])
