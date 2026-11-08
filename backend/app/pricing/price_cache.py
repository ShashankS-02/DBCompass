"""Read/write price snapshots and look prices up by service, component, region, term and dims."""

import json
import logging
from pathlib import Path

from app.models.pricing import PricePoint, PriceSnapshot, Term
from app.pricing.matching import normalise_dim

logger = logging.getLogger(__name__)

SNAPSHOT_DIR_NAME = "price_snapshots"


def snapshot_path(kb_dir: Path, csp: str) -> Path:
    """knowledge_base/price_snapshots/<csp>.json"""
    return kb_dir / SNAPSHOT_DIR_NAME / f"{csp}.json"


def write_snapshot(kb_dir: Path, snapshot: PriceSnapshot) -> Path:
    """Write a snapshot as stable, diff-friendly JSON."""
    path = snapshot_path(kb_dir, snapshot.csp)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot.model_dump(mode="json"), indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return path


def read_snapshots(kb_dir: Path) -> list[PriceSnapshot]:
    """Every snapshot file present (a CSP without one is simply unpriced)."""
    snapshots = []
    for csp in ("aws", "azure", "gcp"):
        path = snapshot_path(kb_dir, csp)
        if path.exists():
            snapshots.append(PriceSnapshot.model_validate_json(path.read_text(encoding="utf-8")))
    return snapshots


class PriceIndex:
    """Fast lookup over all snapshots."""

    def __init__(self, snapshots: list[PriceSnapshot]) -> None:
        self.snapshots = {snapshot.csp: snapshot for snapshot in snapshots}
        self.by_key: dict[tuple[str, str, str, str], list[PricePoint]] = {}
        self.instances: dict[str, set[str]] = {}
        for snapshot in snapshots:
            for price in snapshot.prices:
                key = (price.service_id, price.component_id, price.region, price.term)
                self.by_key.setdefault(key, []).append(price)
                if "instance" in price.dims:
                    self.instances.setdefault(price.service_id, set()).add(price.dims["instance"])

    def offered_instances(self, service_id: str) -> set[str] | None:
        """Instance names with a price for this service, or None when prices are not per instance."""
        return self.instances.get(service_id)

    def lookup(self, service_id: str, component_id: str, region: str, term: Term, wanted_dims: dict[str, str]) -> PricePoint | None:
        """Price whose dims all equal the wanted dims (a price with fewer dims is more general)."""
        normalised_wanted = {name: normalise_dim(str(value)) for name, value in wanted_dims.items()}
        for price in self.by_key.get((service_id, component_id, region, term), []):
            if all(normalised_wanted.get(name) == value for name, value in price.dims.items()):
                return price
        return None

    def regions(self, csp: str) -> list[str]:
        """Regions present in a CSP's snapshot."""
        snapshot = self.snapshots.get(csp)
        return snapshot.regions if snapshot else []

    def fetched_at(self, csp: str) -> str | None:
        """ISO timestamp of a CSP's snapshot."""
        snapshot = self.snapshots.get(csp)
        return snapshot.fetched_at.isoformat() if snapshot else None
