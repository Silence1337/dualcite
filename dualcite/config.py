"""
config.py — load and validate the DualCite configuration.

The config is the single source of truth for everything venue- and
dataset-specific. Nothing in the rest of the codebase hard-codes venue names,
colours, or cluster membership; it all comes from here.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML required:  pip install pyyaml")


@dataclass
class Cluster:
    key: str            # 'a' or 'b'
    name: str
    short: str
    color: str
    venues: list[str]


@dataclass
class Config:
    clusters: dict[str, Cluster]          # {'a': Cluster, 'b': Cluster}
    edge_colors: dict[str, str]
    venue_patterns: dict[str, list[str]]
    data: dict[str, Path]
    schema: dict[str, dict]
    fuzzy_threshold: int
    min_words_for_fuzzy: int
    port: int
    open_browser: bool
    _root: Path = field(default=Path("."))

    # --- convenience accessors -------------------------------------------

    @property
    def venues_a(self) -> list[str]:
        return self.clusters["a"].venues

    @property
    def venues_b(self) -> list[str]:
        return self.clusters["b"].venues

    def cluster_of(self, venue: str) -> str | None:
        """Return 'a' or 'b' for a venue, or None if it belongs to neither."""
        if venue in self.clusters["a"].venues:
            return "a"
        if venue in self.clusters["b"].venues:
            return "b"
        return None

    def color_of_cluster(self, cluster_key: str) -> str:
        return self.clusters[cluster_key].color

    def path(self, key: str) -> Path:
        """Resolve a data path relative to the config file's directory."""
        return (self._root / self.data[key]).resolve()


def load_config(config_path: str | Path = "config.yaml") -> Config:
    path = Path(config_path)
    if not path.exists():
        sys.exit(f"Config file not found: {path}")

    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    _validate(raw, path)

    clusters = {}
    for key in ("a", "b"):
        c = raw["clusters"][key]
        clusters[key] = Cluster(
            key=key,
            name=c["name"],
            short=c.get("short", key.upper()),
            color=c["color"],
            venues=[v.lower() for v in c["venues"]],
        )

    data = {k: Path(v) for k, v in raw["data"].items()}
    matching = raw.get("matching", {})
    server = raw.get("server", {})

    return Config(
        clusters=clusters,
        edge_colors=raw["edge_colors"],
        venue_patterns={k: [p.lower() for p in v]
                        for k, v in raw["venue_patterns"].items()},
        data=data,
        schema=raw["schema"],
        fuzzy_threshold=matching.get("fuzzy_threshold", 85),
        min_words_for_fuzzy=matching.get("min_words_for_fuzzy", 4),
        port=server.get("port", 8050),
        open_browser=server.get("open_browser", True),
        _root=path.parent,
    )


def _validate(raw: dict, path: Path):
    errors = []

    if "clusters" not in raw:
        errors.append("missing 'clusters' section")
    else:
        for key in ("a", "b"):
            if key not in raw["clusters"]:
                errors.append(f"missing cluster '{key}'")
                continue
            c = raw["clusters"][key]
            for field_name in ("name", "color", "venues"):
                if field_name not in c:
                    errors.append(f"cluster '{key}' missing '{field_name}'")
            if "venues" in c and not c["venues"]:
                errors.append(f"cluster '{key}' has empty venue list")

    # venue overlap check — a venue can't be in both clusters
    if not errors and "clusters" in raw:
        va = set(v.lower() for v in raw["clusters"]["a"].get("venues", []))
        vb = set(v.lower() for v in raw["clusters"]["b"].get("venues", []))
        overlap = va & vb
        if overlap:
            errors.append(f"venues in both clusters: {sorted(overlap)}")

    for section in ("edge_colors", "venue_patterns", "data", "schema"):
        if section not in raw:
            errors.append(f"missing '{section}' section")

    if errors:
        msg = "\n  - ".join(errors)
        sys.exit(f"Config errors in {path}:\n  - {msg}")


if __name__ == "__main__":
    # quick self-test
    cfg = load_config(sys.argv[1] if len(sys.argv) > 1 else "config.yaml")
    print(f"Loaded config with clusters:")
    for key, c in cfg.clusters.items():
        print(f"  {key}: {c.name} ({c.short}) — {len(c.venues)} venues: {c.venues}")
    print(f"Fuzzy threshold: {cfg.fuzzy_threshold}")
    print(f"Port: {cfg.port}")
