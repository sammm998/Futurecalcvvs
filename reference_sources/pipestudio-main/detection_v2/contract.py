"""Offline validation against the verified release bundle, plus graph rules."""
import json
import math
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

ROOT = Path(__file__).with_name("contracts")
SCHEMAS = {p.name: json.loads(p.read_text()) for p in ROOT.glob("*.schema.json")}
REGISTRY = Registry().with_resources(
    (s["$id"], Resource.from_contents(s)) for s in SCHEMAS.values())


def validate(kind, body):
    Draft202012Validator(SCHEMAS[f"detection-{kind}.v2.schema.json"],
                        registry=REGISTRY).validate(body)
    # JSON Schema treats Python infinity as a number; wire JSON cannot.
    json.dumps(body, allow_nan=False)


def graph_length(geometry):
    """Sum each undirected edge once, keeping crossings disconnected."""
    nodes = {n["id"]: n for n in geometry["nodes"]}
    if len(nodes) != len(geometry["nodes"]):
        raise ValueError("duplicate node id")
    adjacent = {i: set() for i in nodes}
    seen, length = set(), 0.0
    for a, b in geometry["edges"]:
        if a not in nodes or b not in nodes or a == b:
            raise ValueError("invalid edge reference")
        edge = tuple(sorted((a, b)))
        if edge in seen:
            raise ValueError("duplicate edge")
        seen.add(edge)
        distance = math.hypot(nodes[a]["x"] - nodes[b]["x"],
                              nodes[a]["y"] - nodes[b]["y"])
        if not math.isfinite(distance) or distance <= 0:
            raise ValueError("zero or non-finite edge length")
        length += distance
        adjacent[a].add(b)
        adjacent[b].add(a)
    visited, todo = set(), [next(iter(nodes))]
    while todo:
        n = todo.pop()
        if n not in visited:
            visited.add(n)
            todo.extend(adjacent[n] - visited)
    if len(visited) != len(nodes):
        raise ValueError("disconnected graph")
    return length


def validate_result(body, request):
    validate("result", body)
    if any(body[k] != request[k] for k in ("protocolVersion", "drawingId", "runId")):
        raise ValueError("result identifiers differ from request")
    if body["status"] == "failed":
        return
    space = request["coordinateSpace"]
    if body["coordinateSpace"] != space:
        raise ValueError("coordinate space differs from request")
    include = request["output"]["includeScaleAndLengths"]
    if not include and body["scale"] is not None:
        raise ValueError("unsolicited scale")
    if include and body["scale"] is None and "scale_not_found" not in body["metadata"].get("warnings", []):
        raise ValueError("missing scale warning")
    def point(x, y):
        if not (-1 <= x <= space["width"] + 1 and -1 <= y <= space["height"] + 1):
            raise ValueError("coordinates outside requested canvas")
    for collection in (body["pipes"], body["labels"], body.get("markers", [])):
        if len({v["id"] for v in collection}) != len(collection):
            raise ValueError("duplicate object id")
    labels = {v["id"] for v in body["labels"]}
    total_nodes = total_edges = 0
    for pipe in body["pipes"]:
        if pipe["labelId"] is not None and pipe["labelId"] not in labels:
            raise ValueError("unknown label reference")
        graph = pipe["geometry"]
        graph_length(graph)
        total_nodes += len(graph["nodes"])
        total_edges += len(graph["edges"])
        for node in graph["nodes"]:
            point(node["x"], node["y"])
        if ("length" in pipe) != include:
            raise ValueError("length ownership differs from request")
        if body["scale"] is None and "planView" in pipe.get("length", {}):
            raise ValueError("physical length without scale")
    if total_nodes > 20000 or total_edges > 40000:
        raise ValueError("total graph limit exceeded")
    for item in body["labels"] + body.get("markers", []):
        if item.get("labelId") is not None and item["labelId"] not in labels:
            raise ValueError("unknown marker label reference")
        box = item["box"]
        angle = math.radians(box.get("rotation", 0))
        for dx, dy in ((0, 0), (box["width"], 0), (0, box["height"]), (box["width"], box["height"])):
            point(box["x"] + dx * math.cos(angle) - dy * math.sin(angle),
                  box["y"] + dx * math.sin(angle) + dy * math.cos(angle))
    if len(json.dumps(body, ensure_ascii=False, allow_nan=False).encode()) > 10 * 1024 * 1024:
        raise ValueError("callback exceeds 10 MiB")
