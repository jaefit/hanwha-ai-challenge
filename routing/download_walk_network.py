"""Download and export the pedestrian network around all project CCTV cameras."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import networkx as nx
import osmnx as ox
from pyproj import Transformer
from shapely.geometry import LineString, mapping


ROOT = Path(__file__).resolve().parents[1]
CAMS_PATH = ROOT / "docs" / "data" / "cams.json"
DATA_DIR = ROOT / "data" / "pedestrian"
WEB_DIR = ROOT / "docs" / "data" / "routing"
CACHE_DIR = ROOT / "routing" / "cache"

BUFFER_M = 900.0
GRAPHML_PATH = DATA_DIR / "yeouido_walk.graphml"
GPKG_PATH = DATA_DIR / "yeouido_walk.gpkg"
GEOJSON_PATH = DATA_DIR / "yeouido_walk.geojson"
WEB_GEOJSON_PATH = WEB_DIR / "walk_network.geojson"
WEB_GRAPH_PATH = WEB_DIR / "walk_graph.json"
STATS_PATH = WEB_DIR / "walk_graph_stats.json"


def json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple, set)):
        return ",".join(map(str, value))
    return str(value)


def calculate_bbox(cams: list[dict[str, Any]]) -> tuple[float, float, float, float]:
    """Return OSMnx 2.x bbox order: left, bottom, right, top."""
    mean_lat = sum(float(cam["lat"]) for cam in cams) / len(cams)
    lat_pad = BUFFER_M / 111_320.0
    lon_pad = BUFFER_M / (111_320.0 * math.cos(math.radians(mean_lat)))
    left = min(float(cam["lng"]) for cam in cams) - lon_pad
    bottom = min(float(cam["lat"]) for cam in cams) - lat_pad
    right = max(float(cam["lng"]) for cam in cams) + lon_pad
    top = max(float(cam["lat"]) for cam in cams) + lat_pad
    return left, bottom, right, top


def edge_geometry(graph: nx.MultiDiGraph, u: int, v: int, data: dict[str, Any]):
    geometry = data.get("geometry")
    if geometry is not None:
        return geometry
    return LineString(
        [
            (float(graph.nodes[u]["x"]), float(graph.nodes[u]["y"])),
            (float(graph.nodes[v]["x"]), float(graph.nodes[v]["y"])),
        ]
    )


def export_geojson(graph: nx.MultiDiGraph) -> int:
    features = []
    seen: set[tuple[int, int, int]] = set()
    for u, v, key, data in graph.edges(keys=True, data=True):
        pair = (min(int(u), int(v)), max(int(u), int(v)), int(key))
        if pair in seen:
            continue
        seen.add(pair)
        props = {
            "u": str(u),
            "v": str(v),
            "key": int(key),
            "length_m": round(float(data.get("length", 0.0)), 1),
        }
        for name in ("osmid", "name", "highway", "foot", "sidewalk", "bridge", "tunnel", "layer", "access"):
            if name in data:
                props[name] = json_value(data[name])
        features.append(
            {
                "type": "Feature",
                "properties": props,
                "geometry": mapping(edge_geometry(graph, u, v, data)),
            }
        )
    content = json.dumps(
        {"type": "FeatureCollection", "features": features},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    GEOJSON_PATH.write_text(content, encoding="utf-8")
    WEB_GEOJSON_PATH.write_text(content, encoding="utf-8")
    return len(features)


def export_web_graph(graph: nx.MultiDiGraph) -> None:
    nodes = {
        str(node): [round(float(data["x"]), 7), round(float(data["y"]), 7)]
        for node, data in graph.nodes(data=True)
    }
    edges = []
    for u, v, key, data in graph.edges(keys=True, data=True):
        geom = edge_geometry(graph, u, v, data)
        coords = [[round(float(x), 7), round(float(y), 7)] for x, y in geom.coords]
        edges.append(
            {
                "u": str(u),
                "v": str(v),
                "k": int(key),
                "m": round(float(data.get("length", 0.0)), 1),
                "h": json_value(data.get("highway")),
                "f": json_value(data.get("foot")),
                "s": json_value(data.get("sidewalk")),
                "x": json_value(data.get("crossing")),
                "a": json_value(data.get("access")),
                "sv": json_value(data.get("service")),
                "b": json_value(data.get("bridge")),
                "t": json_value(data.get("tunnel")),
                "g": coords,
            }
        )
    payload = {
        "schema": 1,
        "crs": "EPSG:4326",
        "directed": True,
        "nodes": nodes,
        "edges": edges,
    }
    WEB_GRAPH_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


def camera_snap_report(graph: nx.MultiDiGraph, cams: list[dict[str, Any]]) -> list[dict[str, Any]]:
    projected = ox.projection.project_graph(graph)
    transformer = Transformer.from_crs("EPSG:4326", projected.graph["crs"], always_xy=True)
    xs, ys = transformer.transform(
        [float(cam["lng"]) for cam in cams],
        [float(cam["lat"]) for cam in cams],
    )
    edge_ids, distances = ox.distance.nearest_edges(projected, X=xs, Y=ys, return_dist=True)
    report = []
    for cam, edge_id, distance in zip(cams, edge_ids, distances, strict=True):
        report.append(
            {
                "camId": str(cam["camId"]),
                "name": cam["name"],
                "nearest_edge": [str(edge_id[0]), str(edge_id[1]), int(edge_id[2])],
                "snap_distance_m": round(float(distance), 1),
                "review": bool(distance > 100),
            }
        )
    return report


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    WEB_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cams = json.loads(CAMS_PATH.read_text(encoding="utf-8"))
    bbox = calculate_bbox(cams)

    ox.settings.use_cache = True
    ox.settings.cache_folder = CACHE_DIR
    ox.settings.requests_timeout = 240
    ox.settings.log_console = True
    for tag in ("bridge", "tunnel", "layer", "foot", "sidewalk", "crossing", "access", "wheelchair", "incline"):
        if tag not in ox.settings.useful_tags_way:
            ox.settings.useful_tags_way.append(tag)
    for tag in ("crossing", "highway", "wheelchair"):
        if tag not in ox.settings.useful_tags_node:
            ox.settings.useful_tags_node.append(tag)

    print(f"Downloading walk network for bbox={bbox}")
    graph = ox.graph.graph_from_bbox(
        bbox,
        network_type="walk",
        simplify=True,
        retain_all=True,
        truncate_by_edge=True,
    )

    ox.io.save_graphml(graph, filepath=GRAPHML_PATH)
    ox.io.save_graph_geopackage(graph, filepath=GPKG_PATH, directed=False)
    feature_count = export_geojson(graph)
    export_web_graph(graph)

    weak_components = list(nx.weakly_connected_components(graph))
    largest = max((len(component) for component in weak_components), default=0)
    camera_snaps = camera_snap_report(graph, cams)
    stats = {
        "source": "OpenStreetMap via OSMnx/Overpass",
        "network_type": "walk",
        "bbox": {"left": bbox[0], "bottom": bbox[1], "right": bbox[2], "top": bbox[3]},
        "buffer_m": BUFFER_M,
        "cctv_count": len(cams),
        "nodes": graph.number_of_nodes(),
        "directed_edges": graph.number_of_edges(),
        "display_features": feature_count,
        "weak_components": len(weak_components),
        "largest_component_nodes": largest,
        "largest_component_ratio": round(largest / max(graph.number_of_nodes(), 1), 4),
        "camera_snaps": camera_snaps,
        "attribution": "© OpenStreetMap contributors, ODbL",
    }
    STATS_PATH.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in stats.items() if k != "camera_snaps"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
