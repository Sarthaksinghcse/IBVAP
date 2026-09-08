"""
Zones Module — Spatial Polygon Zones & Flow Vector Configuration
================================================================
Manages restricted/monitored polygon zones per camera source, performs
point-in-polygon tests using Shapely, and provides expected flow direction vectors.
"""
import logging
from typing import List, Tuple, Optional, Dict, Set
from shapely.geometry import Point, Polygon

logger = logging.getLogger("behaviour.zones")


class ZoneDefinition:
    """Represents a spatial security zone polygon with behavioral properties."""

    def __init__(
        self,
        name: str,
        polygon_coords: List[Tuple[float, float]],
        zone_type: str = "restricted",
        expected_flow_deg: Optional[float] = None
    ):
        self.name: str = name
        self.polygon_coords: List[Tuple[float, float]] = polygon_coords
        self.zone_type: str = zone_type.lower()  # "restricted" | "monitored" | "exclusion"
        self.expected_flow_deg: Optional[float] = expected_flow_deg
        self.shapely_polygon: Optional[Polygon] = None

        if polygon_coords and len(polygon_coords) >= 3:
            try:
                self.shapely_polygon = Polygon(polygon_coords)
            except Exception as e:
                logger.error(f"[Zones] Failed to build Polygon '{name}': {e}")

    def contains_point(self, point_xy: Tuple[float, float]) -> bool:
        """Check if a point (x%, y%) lies inside this zone polygon."""
        if self.shapely_polygon is None:
            return False
        try:
            pt = Point(point_xy)
            return self.shapely_polygon.contains(pt) or self.shapely_polygon.touches(pt)
        except Exception as e:
            logger.error(f"[Zones] Error testing point {point_xy} in zone '{self.name}': {e}")
            return False


class ZoneManager:
    """Manages zone definitions for multiple cameras and handles spatial queries."""

    def __init__(self, camera_configs: Optional[dict] = None):
        self.camera_zones: Dict[str, List[ZoneDefinition]] = {}
        if camera_configs:
            self.load_from_config(camera_configs)

    def load_from_config(self, camera_configs: dict) -> None:
        """Load camera zone configurations from dictionary (loaded from YAML)."""
        self.camera_zones.clear()

        for cam_id, cfg in camera_configs.items():
            zones_list = []
            expected_flow = cfg.get("expected_flow_deg")
            raw_zones = cfg.get("zones", [])

            for z_cfg in raw_zones:
                name = z_cfg.get("name", "Zone")
                z_type = z_cfg.get("type", "restricted")
                raw_coords = z_cfg.get("polygon", [])
                flow = z_cfg.get("expected_flow_deg", expected_flow)

                coords = [(float(pt[0]), float(pt[1])) for pt in raw_coords if len(pt) >= 2]
                if len(coords) >= 3:
                    z_def = ZoneDefinition(
                        name=name,
                        polygon_coords=coords,
                        zone_type=z_type,
                        expected_flow_deg=flow
                    )
                    zones_list.append(z_def)

            self.camera_zones[cam_id] = zones_list

    def set_camera_zone(
        self,
        camera_id: str,
        name: str,
        polygon_coords: List[Tuple[float, float]],
        zone_type: str = "restricted",
        expected_flow_deg: Optional[float] = None
    ) -> None:
        """Dynamically add or replace a zone definition for a specific camera."""
        z_def = ZoneDefinition(
            name=name,
            polygon_coords=polygon_coords,
            zone_type=zone_type,
            expected_flow_deg=expected_flow_deg
        )
        if camera_id not in self.camera_zones:
            self.camera_zones[camera_id] = []
        # Replace if zone with same name exists
        self.camera_zones[camera_id] = [z for z in self.camera_zones[camera_id] if z.name != name]
        self.camera_zones[camera_id].append(z_def)

    def get_zones_for_camera(self, camera_id: str) -> List[ZoneDefinition]:
        """Return list of active ZoneDefinitions for a camera (falls back to 'default')."""
        if camera_id in self.camera_zones and self.camera_zones[camera_id]:
            return self.camera_zones[camera_id]
        return self.camera_zones.get("default", [])

    def evaluate_point(self, camera_id: str, point_xy: Tuple[float, float]) -> List[ZoneDefinition]:
        """Return all zones containing the given point (x%, y%)."""
        zones = self.get_zones_for_camera(camera_id)
        matching = []
        for z in zones:
            if z.contains_point(point_xy):
                matching.append(z)
        return matching
