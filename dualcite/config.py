"""
config.py: load and validate the DualCite configuration.

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
    fuzzy_floor: int = 80
    max_year_gap: int = 1
    exclude_patterns: list = field(default_factory=list)
    exclude_title_prefixes: list = field(default_factory=lambda: ["proceedings of"])
    exclude_id_suffixes: list = field(default_factory=list)
    include_id_prefixes: list = field(default_factory=list)
    _root: Path = field(default=Path("."))

    # --- convenience accessors -------------------------------------------

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
        fuzzy_floor=matching.get("fuzzy_candidate_floor", 80),
        max_year_gap=matching.get("max_year_gap", 1),
        exclude_patterns=[x.lower() for x in raw.get("exclude_source_patterns", [])],
        exclude_title_prefixes=[x.lower() for x in raw.get("exclude_title_prefixes", ["proceedings of"])],
        exclude_id_suffixes=list(raw.get("exclude_id_suffixes", [])),
        include_id_prefixes=list(raw.get("include_id_prefixes", [])),
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

    # venue overlap check, a venue can't be in both clusters
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

    # a venue without patterns is only recognized when a record names it directly,
    # and never in cited venue names; warn instead of failing silently
    known = {k.lower() for k in (raw.get("venue_patterns") or {})}
    for key in ("a", "b"):
        for v in raw["clusters"][key].get("venues", []):
            if v.lower() not in known:
                print(f"  warning: venue '{v}' has no entry in venue_patterns; it is only "
                      f"recognized where a record's venue field names it directly",
                      file=sys.stderr)


if __name__ == "__main__":
    # quick self-test
    cfg = load_config(sys.argv[1] if len(sys.argv) > 1 else "config.yaml")
    print("Loaded config with clusters:")
    for key, c in cfg.clusters.items():
        print(f"  {key}: {c.name} ({c.short}), {len(c.venues)} venues: {c.venues}")
    print(f"Fuzzy threshold: {cfg.fuzzy_threshold}")
    print(f"Port: {cfg.port}")
