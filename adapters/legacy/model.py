"""Exact Contact and Graph excerpts needed by the historical CHILS adapter."""
from __future__ import annotations
from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
import math
from typing import Iterable

@dataclass(frozen=True)
class Contact:
    id: str
    weight: float
    satellite: str
    station: str
    start: float
    end: float
    task: str = ""


@dataclass
class Graph:
    name: str
    contacts: tuple[Contact, ...]
    edges: frozenset[tuple[str, str]]
    constraints: dict = field(default_factory=dict)
    provenance: dict = field(default_factory=dict)

    def __post_init__(self):
        self.nodes = {c.id: c for c in self.contacts}
        if len(self.nodes) != len(self.contacts):
            raise ValueError("Duplicate contact ids")
        for c in self.contacts:
            if not all(math.isfinite(v) for v in (c.weight, c.start, c.end)) or c.weight < 0 or c.end <= c.start:
                raise ValueError("Contacts require finite nonnegative weights and positive duration")
        try:
            if not math.isfinite(math.fsum(c.weight for c in self.contacts)):
                raise ValueError("Total graph weight must be representable")
        except OverflowError as error:
            raise ValueError("Total graph weight must be representable") from error
        canonical = set()
        for a, b in self.edges:
            if a == b or a not in self.nodes or b not in self.nodes:
                raise ValueError("Invalid graph edge")
            canonical.add(tuple(sorted((a, b))))
        self.edges = frozenset(canonical)
        self.adj = {k: set() for k in self.nodes}
        for a, b in self.edges:
            self.adj[a].add(b)
            self.adj[b].add(a)

    def feasible(self, selected: Iterable[str]) -> bool:
        ids = tuple(selected)
        chosen = set(ids)
        return len(ids) == len(chosen) and chosen <= self.nodes.keys() and all(
            not self.adj[v].intersection(chosen) for v in chosen
        )

    def value(self, selected: Iterable[str]) -> float:
        return math.fsum(self.nodes[v].weight for v in selected)

    def available(self, fixed=(), excluded=()) -> set[str]:
        fixed = tuple(fixed)
        excluded = set(excluded)
        if not set(excluded) <= self.nodes.keys():
            raise ValueError("Unknown excluded node")
        if not self.feasible(fixed) or set(fixed).intersection(excluded):
            raise ValueError("Invalid fixed boundary")
        blocked = set(fixed) | set(excluded)
        for v in fixed:
            blocked.update(self.adj[v])
        return set(self.nodes) - blocked

    def to_dict(self) -> dict:
        return {"name": self.name, "contacts": [asdict(c) for c in self.contacts],
                "edges": [list(e) for e in sorted(self.edges)],
                "constraints": self.constraints, "provenance": self.provenance}

    @classmethod
    def from_dict(cls, d):
        return cls(d["name"], tuple(Contact(**c) for c in d["contacts"]),
                   frozenset(tuple(e) for e in d["edges"]), d.get("constraints", {}),
                   d.get("provenance", {}))

    def digest(self) -> str:
        d = self.to_dict()
        d.pop("name")
        d.pop("provenance")
        return sha256(json.dumps(d, sort_keys=True).encode()).hexdigest()

