"""序列化辅助。"""
from . import models


def user_out(u: models.User) -> dict:
    roles = u.role.split(",")
    return {
        "id": u.id, "username": u.username, "name": u.name,
        "role": u.role,
        "roles": roles,
        "role_name": "、".join(models.ROLE_NAMES.get(r, r) for r in roles),
        "perms": {
            "can_dispatch": models.ROLE_DISPATCHER in roles,
            "can_work": models.ROLE_OPERATOR in roles,
            "can_review": models.ROLE_REVIEWER in roles,
            "can_manage": models.ROLE_MANAGER in roles,
        },
    }


def vehicle_out(v: models.Vehicle) -> dict:
    return {
        "id": v.id, "plate": v.plate, "min_level": v.min_level,
        "capacity_kg": v.capacity_kg, "status": v.status,
        "operator_id": v.operator_id,
        "operator_name": v.operator.name if v.operator else None,
        "current_segment_id": v.current_segment_id,
    }


def segment_out(s: models.RoadSegment) -> dict:
    return {
        "id": s.id, "code": s.code, "name": s.name,
        "road_level": s.road_level,
        "road_level_name": models.ROAD_LEVELS.get(s.road_level, str(s.road_level)),
        "length_km": s.length_km, "geometry": s.geometry,
        "status": s.status,
        "status_name": models.SEGMENT_STATUS_NAMES.get(s.status, s.status),
        "salt_total_kg": round(s.salt_total_kg, 2),
        "current_dispatch_id": s.current_dispatch_id,
        "opened_at": s.opened_at,
    }


def record_out(r: models.WorkRecord, duplicate: bool = False) -> dict:
    return {
        "id": r.id, "dispatch_id": r.dispatch_id, "segment_id": r.segment_id,
        "vehicle_id": r.vehicle_id,
        "operator_name": r.operator.name if r.operator else str(r.operator_id),
        "worked_at": r.worked_at, "salt_kg": r.salt_kg,
        "photo_url": f"/api/photos/{r.id}" if r.photo_path else None,
        "pos_x": r.pos_x, "pos_y": r.pos_y,
        "client_token": r.client_token, "created_at": r.created_at,
        "duplicate": duplicate,
    }


def breakdown_out(b: models.Breakdown) -> dict:
    return {
        "id": b.id, "dispatch_id": b.dispatch_id, "vehicle_id": b.vehicle_id,
        "vehicle_plate": b.vehicle.plate if b.vehicle else str(b.vehicle_id),
        "operator_name": b.operator.name if b.operator else str(b.operator_id),
        "occurred_at": b.occurred_at, "reason": b.reason,
        "follow_up": b.follow_up, "status": b.status, "created_at": b.created_at,
    }


def dispatch_out(d: models.Dispatch) -> dict:
    return {
        "id": d.id, "segment_id": d.segment_id, "vehicle_id": d.vehicle_id,
        "vehicle_plate": d.vehicle.plate if d.vehicle else str(d.vehicle_id),
        "dispatcher_name": d.dispatcher.name if d.dispatcher else str(d.dispatcher_id),
        "salt_planned_kg": d.salt_planned_kg, "status": d.status,
        "note": d.note, "created_at": d.created_at, "completed_at": d.completed_at,
        "records": [record_out(r) for r in d.records],
        "breakdowns": [breakdown_out(b) for b in d.breakdowns],
    }


def review_out(r: models.Review) -> dict:
    return {
        "id": r.id, "segment_id": r.segment_id,
        "reviewer_name": r.reviewer.name if r.reviewer else str(r.reviewer_id),
        "passed": r.passed, "snow_cleared": r.snow_cleared,
        "surface_safe": r.surface_safe, "note": r.note,
        "reviewed_at": r.reviewed_at,
    }
