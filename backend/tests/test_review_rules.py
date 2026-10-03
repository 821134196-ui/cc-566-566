"""验证复核权限与状态流转：
- 只有复核员能开放路段；调度员/作业人员/管理人员都不能；
- 作业人员不能签发自己负责路段的开放结论（即使其兼具备复核身份）；
- 未进入待复核的路段不能被复核，未复核通过前不会提前开放。
"""
from .conftest import (
    Api, DISPATCHER, REVIEWER, MANAGER, OP_LI, OP_CHEN, OP_SUN,
    SEG_R101, SEG_R201, VEH_X101, VEH_X201,
)


def _prepare_in_review(client, segment_id=SEG_R101, vehicle_id=VEH_X101, op_name=OP_LI):
    disp = Api(client).login(DISPATCHER)
    op = Api(client).login(op_name)
    d = disp.post("/api/dispatches", json={
        "segment_id": segment_id, "vehicle_id": vehicle_id}).json()["id"]
    op.post("/api/work-records", json={
        "dispatch_id": d, "salt_kg": 500, "pos_x": 0.3, "pos_y": 0.22,
        "client_token": "t1"})
    op.post("/api/dispatches/complete", json={"dispatch_id": d})
    return disp, op, d


def test_operator_cannot_open_own_segment_even_if_also_reviewer(client):
    # chen 同时是作业人员与复核员，驾驶 X201 在二级路 R201 作业
    disp, op, _ = _prepare_in_review(client, SEG_R201, VEH_X201, OP_CHEN)

    # chen 试图以复核身份签发自己作业路段 → 必须拒绝
    r = op.post("/api/reviews", json={
        "segment_id": SEG_R201, "snow_cleared": True, "surface_safe": True})
    assert r.status_code == 403, r.text
    assert "职责分离" in r.json()["detail"]

    seg = disp.get(f"/api/segments/{SEG_R201}/detail").json()
    assert seg["status"] == "in_review"   # 仍是待复核，没有被开放


def test_independent_reviewer_can_pass(client):
    disp, op, _ = _prepare_in_review(client)
    rev = Api(client).login(REVIEWER)
    r = rev.post("/api/reviews", json={
        "segment_id": SEG_R101, "snow_cleared": True, "surface_safe": True})
    assert r.status_code == 200
    assert r.json()["passed"] is True
    assert disp.get(f"/api/segments/{SEG_R101}/detail").json()["status"] == "open"


def test_dispatcher_operator_manager_have_no_review_permission(client):
    _prepare_in_review(client)
    for username in (DISPATCHER, OP_LI, MANAGER):
        u = Api(client).login(username)
        r = u.post("/api/reviews", json={
            "segment_id": SEG_R101, "snow_cleared": True, "surface_safe": True})
        assert r.status_code == 403, (username, r.text)

    seg = Api(client).login(REVIEWER).get(f"/api/segments/{SEG_R101}/detail").json()
    assert seg["status"] == "in_review"


def test_cannot_review_before_submitted(client):
    # 全新路段处于 untreated，没有派车、没有申请复核
    rev = Api(client).login(REVIEWER)
    r = rev.post("/api/reviews", json={
        "segment_id": SEG_R101, "snow_cleared": True, "surface_safe": True})
    assert r.status_code == 409
    seg = rev.get(f"/api/segments/{SEG_R101}/detail").json()
    assert seg["status"] == "untreated"


def test_segment_not_open_until_review_passes(client):
    # 已撒盐但未点完成 → salted；完成后 → in_review；两者都不是 open
    disp = Api(client).login(DISPATCHER)
    op = Api(client).login(OP_LI)
    d = disp.post("/api/dispatches", json={
        "segment_id": SEG_R101, "vehicle_id": VEH_X101}).json()["id"]
    op.post("/api/work-records", json={
        "dispatch_id": d, "salt_kg": 500, "pos_x": 0.3, "pos_y": 0.22,
        "client_token": "t1"})

    seg = disp.get(f"/api/segments/{SEG_R101}/detail").json()
    assert seg["status"] == "salted"          # 撒过盐但未申请复核
    assert seg["status"] != "open"

    op.post("/api/dispatches/complete", json={"dispatch_id": d})
    seg = disp.get(f"/api/segments/{SEG_R101}/detail").json()
    assert seg["status"] == "in_review"       # 待复核
    assert seg["status"] != "open"


def test_cannot_complete_without_work_records(client):
    disp = Api(client).login(DISPATCHER)
    op = Api(client).login(OP_LI)
    d = disp.post("/api/dispatches", json={
        "segment_id": SEG_R101, "vehicle_id": VEH_X101}).json()["id"]
    r = op.post("/api/dispatches/complete", json={"dispatch_id": d})
    assert r.status_code == 400
    seg = disp.get(f"/api/segments/{SEG_R101}/detail").json()
    assert seg["status"] == "untreated"


def test_reviewer_who_did_not_work_but_other_operator_did_can_review(client):
    # chen 作业 R201；li 虽同为作业人员但没碰过 R201 且不具复核身份 → 403（无复核角色）
    # reviewer 独立第三方 → 可复核。这里确认“碰没碰过该路段”按路段精确判定
    disp, op, _ = _prepare_in_review(client, SEG_R201, VEH_X201, OP_CHEN)
    rev = Api(client).login(REVIEWER)
    r = rev.post("/api/reviews", json={
        "segment_id": SEG_R201, "snow_cleared": True, "surface_safe": True})
    assert r.status_code == 200
    assert disp.get(f"/api/segments/{SEG_R201}/detail").json()["status"] == "open"
