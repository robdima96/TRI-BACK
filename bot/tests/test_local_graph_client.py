"""Tests for local CSV graph client."""

from __future__ import annotations

from app.services.graphrag.local_graph import (
    LocalGraphClient,
    get_graph_client,
    reset_graph_client_cache,
)
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


def test_get_graph_client_is_process_wide_singleton():
    reset_graph_client_cache()
    a = get_graph_client()
    b = get_graph_client()
    assert a is b
    reset_graph_client_cache()
    c = get_graph_client()
    assert c is not a
