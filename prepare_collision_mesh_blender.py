#!/usr/bin/env python3
"""Create a unioned, decimated collision OBJ while preserving source provenance.

Run with Blender, for example:
  blender -b --python prepare_collision_mesh_blender.py -- source.obj collision.obj \
      --voxel-size-m 0.002 --target-faces 10000
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sys

import bpy


UNIT_TO_M = {"m": 1.0, "mm": 0.001, "cm": 0.01, "in": 0.0254}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--voxel-size-m", type=float, default=0.002)
    parser.add_argument("--target-faces", type=int, default=10000)
    parser.add_argument("--source-units", choices=tuple(UNIT_TO_M), default="m")
    return parser.parse_args(argv)


def mesh_bounds(obj) -> dict[str, list[float]]:
    vertices = [obj.matrix_world @ vertex.co for vertex in obj.data.vertices]
    return {
        axis: [min(vertex[index] for vertex in vertices), max(vertex[index] for vertex in vertices)]
        for index, axis in enumerate(("x_m", "y_m", "z_m"))
    }


def fill_triangular_obj_holes(path: Path) -> dict[str, int]:
    """Close tiny three-edge seams left when validation removes duplicate faces."""
    lines = path.read_text().splitlines()
    faces = []
    for line in lines:
        parts = line.split()
        if parts[:1] == ["f"]:
            faces.append(tuple(int(token.split("/", 1)[0]) for token in parts[1:]))
    edge_use = Counter()
    directed_edges = set()
    for face in faces:
        for start, end in zip(face, face[1:] + face[:1]):
            edge_use[tuple(sorted((start, end)))] += 1
            directed_edges.add((start, end))
    boundary = [edge for edge, uses in edge_use.items() if uses == 1]
    graph = defaultdict(list)
    for start, end in boundary:
        graph[start].append(end)
        graph[end].append(start)
    seen = set()
    fills = []
    unfilled_edges = 0
    for vertex in graph:
        if vertex in seen:
            continue
        stack = [vertex]
        component = []
        seen.add(vertex)
        while stack:
            current = stack.pop()
            component.append(current)
            for neighbor in graph[current]:
                if neighbor not in seen:
                    seen.add(neighbor)
                    stack.append(neighbor)
        if len(component) == 3 and all(len(graph[item]) == 2 for item in component):
            start = min(component)
            second = graph[start][0]
            third = next(item for item in graph[second] if item != start)
            boundary_cycle = (start, second, third)
            if not all(
                edge in directed_edges
                for edge in zip(boundary_cycle, boundary_cycle[1:] + boundary_cycle[:1])
            ):
                boundary_cycle = (start, third, second)
            fills.append((boundary_cycle[0], boundary_cycle[2], boundary_cycle[1]))
        else:
            unfilled_edges += sum(len(graph[item]) for item in component) // 2
    if fills:
        lines.append("# Closed triangular validation seams")
        lines.extend("f " + " ".join(str(index) for index in face) for face in fills)
        path.write_text("\n".join(lines) + "\n")
    return {
        "triangular_holes_filled": len(fills),
        "boundary_edges_not_filled": unfilled_edges,
    }


def main() -> None:
    args = parse_args()
    source = args.source.resolve()
    destination = args.destination.resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    if args.voxel_size_m <= 0 or args.target_faces < 100:
        raise ValueError("voxel size must be positive and target faces must be at least 100")

    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    bpy.ops.wm.obj_import(filepath=str(source))
    meshes = [obj for obj in bpy.context.selected_objects if obj.type == "MESH"]
    if not meshes:
        raise RuntimeError("OBJ import created no mesh objects")
    bpy.context.view_layer.objects.active = meshes[0]
    for obj in meshes:
        obj.select_set(True)
    if len(meshes) > 1:
        bpy.ops.object.join()
    obj = bpy.context.view_layer.objects.active
    scale = UNIT_TO_M[args.source_units]
    obj.scale = (scale, scale, scale)
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)

    source_stats = {
        "vertices": len(obj.data.vertices),
        "polygons": len(obj.data.polygons),
        "bounds": mesh_bounds(obj),
    }
    obj.data.remesh_voxel_size = args.voxel_size_m
    obj.data.remesh_voxel_adaptivity = 0.0
    obj.data.use_remesh_preserve_volume = True
    bpy.ops.object.voxel_remesh()

    after_union_faces = len(obj.data.polygons)
    if after_union_faces > args.target_faces:
        modifier = obj.modifiers.new(name="CollisionDecimate", type="DECIMATE")
        modifier.decimate_type = "COLLAPSE"
        modifier.ratio = args.target_faces / after_union_faces
        modifier.use_collapse_triangulate = True
        bpy.ops.object.modifier_apply(modifier=modifier.name)

    triangulate = obj.modifiers.new(name="CollisionTriangulate", type="TRIANGULATE")
    bpy.ops.object.modifier_apply(modifier=triangulate.name)
    obj.data.validate(verbose=True, clean_customdata=True)
    obj.data.update()

    # Decimation can expose tiny seams where duplicate triangles were removed.
    # Close only boundary loops, then retriangulate so DEM preflight can enforce
    # a strict watertight two-manifold collision surface.
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="DESELECT")
    bpy.ops.mesh.select_non_manifold(
        extend=False,
        use_wire=False,
        use_boundary=True,
        use_multi_face=False,
        use_non_contiguous=False,
        use_verts=False,
    )
    bpy.ops.mesh.fill_holes(sides=0)
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.object.mode_set(mode="OBJECT")
    retriangulate = obj.modifiers.new(name="CollisionRetriangulate", type="TRIANGULATE")
    bpy.ops.object.modifier_apply(modifier=retriangulate.name)
    obj.data.validate(verbose=True, clean_customdata=True)
    obj.data.update()

    destination.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.wm.obj_export(
        filepath=str(destination),
        export_selected_objects=True,
        export_materials=False,
        export_triangulated_mesh=True,
        forward_axis="NEGATIVE_Z",
        up_axis="Y",
    )
    hole_repair = fill_triangular_obj_holes(destination)

    sidecar = {
        "schema_version": 1,
        "method": "Blender voxel union followed by collapse decimation and triangulation",
        "blender_version": bpy.app.version_string,
        "source": str(source),
        "source_sha256": sha256_file(source),
        "source_units": args.source_units,
        "source_scale_to_m": scale,
        "source_mesh": source_stats,
        "voxel_size_m": args.voxel_size_m,
        "target_faces": args.target_faces,
        "after_voxel_union_faces": after_union_faces,
        "collision_mesh": {
            "path": str(destination),
            "sha256": sha256_file(destination),
            "vertices": len(obj.data.vertices),
            "polygons": len(obj.data.polygons) + hole_repair["triangular_holes_filled"],
            "bounds": mesh_bounds(obj),
            **hole_repair,
        },
        "qualification": (
            "Derived collision geometry for numerical screening. The source CAD/OBJ remains "
            "the geometry authority and dimensional deviations must pass case preflight."
        ),
    }
    destination.with_suffix(destination.suffix + ".provenance.json").write_text(
        json.dumps(sidecar, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps(sidecar, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
