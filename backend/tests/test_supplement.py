"""验证：同一路段再次撒盐要追加新作业记录，不能覆盖首次记录。

场景：首次撒盐 → 待复核 → 复核员驳回（需补盐）→ 调度员再次派车 →
追加新派车单与新作业记录；首次记录原样保留，盐量在路段上累加。
"""
from .conftest import (
    Api, DISPATCHER, REVIEWER, OP_LI, SEG_R201, VEH_X101,
)


def _do_first_round_then_reject(client):
    disp = Api(client).login(DISPATCHER)
    op = Api(client).login(OP_LI)
    rev = Api(client).login(REVIEWER)

    r = disp.post("/api/dispatches", json={
        "segment_id": SEG_R201, "vehicle_id": VEH_X101, "salt_planned_kg": 800})
    d1 = r.json()["id"]

    op.post("/api/work-records", json={
        "dispatch_id": d1, "salt_kg": 600, "pos_x": 0.20, "pos_y": 0.30,
        "client_token": "first-1"})
    op.post("/api/work-records", json={
        "dispatch_id": d1, "salt_kg": 200, "pos_x": 0.20, "pos_y": 0.55,
        "client_token": "first-2"})
    op.post("/api/dispatches/complete", json={"dispatch_id": d1})
    assert disp.get(f"/api/segments/{SEG_R201}/detail").json()["status"] == "in_review"

    # 复核不达标，驳回
    r = rev.post("/api/reviews", json={
        "segment_id": SEG_R201, "snow_cleared": True, "surface_safe": False,
        "note": "路面仍有结冰"})
    assert r.status_code == 200
    assert r.json()["passed"] is False
    return disp, op, rev, d1


def test_reject_returns_to_salted_and_keeps_history(client):
    disp, op, rev, d1 = _do_first_round_then_reject(client)
    seg = disp.get(f"/api/segments/{SEG_R201}/detail").json()
    assert seg["status"] == "salted"
    assert seg["salt_total_kg"] == 800
    assert len(seg["dispatches"]) == 1
    assert len(seg["dispatches"][0]["records"]) == 2  # 首次两条记录仍在


def test_supplemental_salting_appends_not_overwrites(client):
    disp, op, rev, d1 = _do_first_round_then_reject(client)

    # 再次派车补盐（同一路段、同一车辆）
    r = disp.post("/api/dispatches", json={
        "segment_id": SEG_R201, "vehicle_id": VEH_X101, "salt_planned_kg": 400,
        "note": "复核驳回，补撒"})
    assert r.status_code == 200, r.text
    d2 = r.json()["id"]
    assert d2 != d1

    # 追加新的作业记录
    r = op.post("/api/work-records", json={
        "dispatch_id": d2, "salt_kg": 350, "pos_x": 0.20, "pos_y": 0.80,
        "client_token": "supp-1"})
    assert r.status_code == 200

    seg = disp.get(f"/api/segments/{SEG_R201}/detail").json()
    assert len(seg["dispatches"]) == 2                 # 两张派车单
    first, second = seg["dispatches"]
    assert len(first["records"]) == 2                 # 首次记录未被覆盖
    assert first["records"][0]["salt_kg"] == 600
    assert len(second["records"]) == 1                # 补盐新记录追加
    assert second["records"][0]["salt_kg"] == 350
    assert seg["salt_total_kg"] == 1150               # 800 + 350 累加


def test_segment_can_open_after_supplement_and_passing_review(client):
    disp, op, rev, _ = _do_first_round_then_reject(client)
    d2 = disp.post("/api/dispatches", json={
        "segment_id": SEG_R201, "vehicle_id": VEH_X101}).json()["id"]
    op.post("/api/work-records", json={
        "dispatch_id": d2, "salt_kg": 350, "pos_x": 0.20, "pos_y": 0.80,
        "client_token": "supp-1"})
    op.post("/api/dispatches/complete", json={"dispatch_id": d2})

    r = rev.post("/api/reviews", json={
        "segment_id": SEG_R201, "snow_cleared": True, "surface_safe": True})
    assert r.status_code == 200 and r.json()["passed"] is True

    seg = disp.get(f"/api/segments/{SEG_R201}/detail").json()
    assert seg["status"] == "open"
    assert seg["opened_at"] is not None
