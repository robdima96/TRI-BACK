"""Tests for local CSV graph client."""

from __future__ import annotations

from app.services.graphrag.local_graph import LocalGraphClient
from app.services.graphrag.neo4j_config import DEFAULT_CSV_PATH


def test_paths_for_factors_fracture():
    client = LocalGraphClient(csv_path=DEFAULT_CSV_PATH)
    segments = client.paths_for_factors(["Recent trauma", "Severe pain"])
    conditions = {s.condition for s in segments}
    assert "Fracture" in conditions
    assert segments
    client.close()


def test_paths_for_chunks():
    client = LocalGraphClient(csv_path=DEFAULT_CSV_PATH)
    segments = client.paths_for_chunks(["r_2"])
    assert len(segments) >= 1
    assert segments[0].chunk_id == "r_2"
    assert segments[0].condition == "Fracture"
    client.close()


def test_paths_for_seeds_dedupes():
    client = LocalGraphClient(csv_path=DEFAULT_CSV_PATH)
    segments = client.paths_for_seeds(["Recent trauma"], ["r_2"])
    keys = {(s.factor, s.condition, s.chunk_id) for s in segments}
    assert len(keys) == len(segments)
    client.close()
