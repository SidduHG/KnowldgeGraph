"""Lightweight metrics registry.

Emits Prometheus exposition format from a single endpoint. We intentionally
do **not** depend on the official prometheus_client library — that pulls in
WSGI middleware we don't need. The wire format is dead simple.

Usage::

    from ckg.observability import counter, histogram

    counter("ckg_index_runs_total", labels={"status": "ok"}).inc()
    with histogram("ckg_parse_seconds", labels={"lang": "python"}).time():
        parser.parse_file(path)

Then expose ``registry.render()`` from any HTTP endpoint.
"""
from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Dict, Iterator, List, Optional, Tuple


_HIST_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
_LabelKey = Tuple[Tuple[str, str], ...]


def _label_key(labels: Optional[Dict[str, str]]) -> _LabelKey:
    if not labels:
        return ()
    return tuple(sorted(labels.items()))


def _fmt_labels(key: _LabelKey) -> str:
    if not key:
        return ""
    inner = ",".join(f'{k}="{v}"' for k, v in key)
    return "{" + inner + "}"


@dataclass
class _Counter:
    name: str
    help: str
    values: Dict[_LabelKey, float] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def inc(self, amount: float = 1.0, *, labels: Optional[Dict[str, str]] = None) -> None:
        key = _label_key(labels)
        with self._lock:
            self.values[key] = self.values.get(key, 0.0) + amount

    def render(self) -> str:
        out = [f"# HELP {self.name} {self.help}", f"# TYPE {self.name} counter"]
        with self._lock:
            for key, value in self.values.items():
                out.append(f"{self.name}{_fmt_labels(key)} {value}")
        return "\n".join(out)


@dataclass
class _Histogram:
    name: str
    help: str
    buckets: Tuple[float, ...] = _HIST_BUCKETS
    counts: Dict[_LabelKey, List[int]] = field(default_factory=dict)
    sums: Dict[_LabelKey, float] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def observe(self, value: float, *, labels: Optional[Dict[str, str]] = None) -> None:
        key = _label_key(labels)
        with self._lock:
            counts = self.counts.setdefault(key, [0] * (len(self.buckets) + 1))
            for i, b in enumerate(self.buckets):
                if value <= b:
                    counts[i] += 1
            counts[-1] += 1  # +Inf bucket / count
            self.sums[key] = self.sums.get(key, 0.0) + value

    @contextmanager
    def time(self, *, labels: Optional[Dict[str, str]] = None) -> Iterator[None]:
        start = time.perf_counter()
        try:
            yield
        finally:
            self.observe(time.perf_counter() - start, labels=labels)

    def render(self) -> str:
        out = [f"# HELP {self.name} {self.help}", f"# TYPE {self.name} histogram"]
        with self._lock:
            for key, counts in self.counts.items():
                lbls = list(key)
                cum = 0
                for i, b in enumerate(self.buckets):
                    cum += counts[i]
                    bucket_lbls = lbls + [("le", str(b))]
                    out.append(f"{self.name}_bucket{_fmt_labels(tuple(bucket_lbls))} {cum}")
                cum += 0  # bucket counts are not cumulative in our store
                inf_lbls = lbls + [("le", "+Inf")]
                out.append(f"{self.name}_bucket{_fmt_labels(tuple(inf_lbls))} {counts[-1]}")
                out.append(f"{self.name}_sum{_fmt_labels(tuple(lbls))} {self.sums.get(key, 0.0)}")
                out.append(f"{self.name}_count{_fmt_labels(tuple(lbls))} {counts[-1]}")
        return "\n".join(out)


class _Registry:
    """Process-wide metric registry — also implements the get-or-create pattern."""

    def __init__(self) -> None:
        self._counters: Dict[str, _Counter] = {}
        self._histograms: Dict[str, _Histogram] = {}
        self._lock = threading.Lock()

    def counter(self, name: str, help: str = "") -> _Counter:
        with self._lock:
            if name not in self._counters:
                self._counters[name] = _Counter(name, help or name)
            return self._counters[name]

    def histogram(self, name: str, help: str = "") -> _Histogram:
        with self._lock:
            if name not in self._histograms:
                self._histograms[name] = _Histogram(name, help or name)
            return self._histograms[name]

    def render(self) -> str:
        parts: List[str] = []
        with self._lock:
            for c in self._counters.values():
                parts.append(c.render())
            for h in self._histograms.values():
                parts.append(h.render())
        return "\n".join(parts) + "\n"


registry = _Registry()


def counter(name: str, help: str = "", labels: Optional[Dict[str, str]] = None) -> _Counter:
    """Get-or-create + optional immediate label binding."""
    c = registry.counter(name, help)
    if labels:
        # Touch the labelled series so it shows up in /metrics even before .inc()
        c.values.setdefault(_label_key(labels), 0.0)
    return c


def histogram(name: str, help: str = "") -> _Histogram:
    return registry.histogram(name, help)
