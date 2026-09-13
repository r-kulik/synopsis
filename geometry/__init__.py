"""World-coordinate geometry used by the map projection."""

from .polyline import control_to_world, world_to_control, edge_path

__all__ = ["control_to_world", "world_to_control", "edge_path"]
