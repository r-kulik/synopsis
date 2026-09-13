"""Endpoint-relative polyline calculations (ADR-001 D-10)."""
from synopsis_domain import Point, RelativeControlPoint


def control_to_world(source: Point, target: Point, point: RelativeControlPoint) -> Point:
    dx, dy = target.x - source.x, target.y - source.y
    return Point(source.x + point.u * dx - point.v * dy, source.y + point.u * dy + point.v * dx)


def world_to_control(source: Point, target: Point, point: Point) -> RelativeControlPoint:
    dx, dy = target.x - source.x, target.y - source.y
    length_squared = dx * dx + dy * dy
    if length_squared == 0:
        raise ValueError("cannot set a relative control point on coincident endpoints")
    px, py = point.x - source.x, point.y - source.y
    return RelativeControlPoint((px * dx + py * dy) / length_squared,
                                (px * -dy + py * dx) / length_squared)


def edge_path(source: Point, target: Point, controls: list[RelativeControlPoint]) -> list[Point]:
    return [source, *(control_to_world(source, target, point) for point in controls), target]
