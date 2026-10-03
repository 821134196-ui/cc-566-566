"""验证：重复定位 / 重复作业回传不能多算融雪剂用量。"""
from .conftest import Api, DISPATCHER, OP_LI, SEG_R101, VEH_X101


def _dispatch_and_upload(disp, op, salt=500.0, pos=(0.3, 0.22), token=None):
    r = disp.post("/api/dispatches", json={
        "segment_id": SEG_R101, "vehicle_id": VEH_X101, "salt_planned_kg": 1000})
    assert r.status_code == 200, r.text
    did = r.json()["id"]

    payload = {"dispatch_id": did, "salt_kg": salt, "pos_x": pos[0], "pos_y": pos[1]}
    if token is not None:
        payload["client_token"] = token
    r = op.post("/api/work-records", json=payload)
    assert r.status_code == 200, r.text
    return did, r.json()


def _detail(disp):
    return disp.get(f"/api/segments/{SEG_R101}/detail").json()


def test_duplicate_token_does_not_double_count_salt(client):
    disp = Api(client).login(DISPATCHER)
    op = Api(client).login(OP_LI)

    did, first = _dispatch_and_upload(disp, op, salt=500, token="mobile-uuid-1")
    assert first["duplicate"] is False

    # 网络重试导致的完全相同回传：同一 client_token
    r = op.post("/api/work-records", json={
        "dispatch_id": did, "salt_kg": 500, "pos_x": 0.3, "pos_y": 0.22,
        "client_token": "mobile-uuid-1"})
    assert r.status_code == 200, r.text
    second = r.json()
    assert second["duplicate"] is True
    assert second["id"] == first["id"]  # 返回原记录，没有新增

    seg = _detail(disp)
    assert seg["salt_total_kg"] == 500          # 没有变成 1000
    assert len(seg["dispatches"][0]["records"]) == 1


def test_duplicate_position_and_salt_deduped_even_without_token(client):
    disp = Api(client).login(DISPATCHER)
    op = Api(client).login(OP_LI)

    did, first = _dispatch_and_upload(disp, op, salt=480, pos=(0.55, 0.22))

    # 同一定位点、同一用量短时间再次回传（无 token）→ 视为重复
    r = op.post("/api/work-records", json={
        "dispatch_id": did, "salt_kg": 480.2, "pos_x": 0.5501, "pos_y": 0.2201})
    assert r.status_code == 200
    body = r.json()
    assert body["duplicate"] is True
    assert body["id"] == first["id"]

    seg = _detail(disp)
    assert seg["salt_total_kg"] == 480


def test_different_position_is_new_work_not_duplicate(client):
    disp = Api(client).login(DISPATCHER)
    op = Api(client).login(OP_LI)

    did, _ = _dispatch_and_upload(disp, op, salt=500, pos=(0.30, 0.22), token="a")
    r = op.post("/api/work-records", json={
        "dispatch_id": did, "salt_kg": 500, "pos_x": 0.80, "pos_y": 0.22,
        "client_token": "b"})
    assert r.status_code == 200
    assert r.json()["duplicate"] is False

    seg = _detail(disp)
    assert seg["salt_total_kg"] == 1000
    assert len(seg["dispatches"][0]["records"]) == 2


def test_duplicate_ignored_entry_is_audited(client):
    """重复回传虽不计盐量，但要有审计轨迹可查。"""
    disp = Api(client).login(DISPATCHER)
    op = Api(client).login(OP_LI)
    did, _ = _dispatch_and_upload(disp, op, salt=300, token="evt-9")
    op.post("/api/work-records", json={
        "dispatch_id": did, "salt_kg": 300, "pos_x": 0.3, "pos_y": 0.22,
        "client_token": "evt-9"})

    timeline = disp.get(f"/api/segments/{SEG_R101}/timeline").json()
    actions = [e["action"] for e in timeline]
    assert "duplicate_upload_ignored" in actions
