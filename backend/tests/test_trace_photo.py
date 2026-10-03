"""验证：每次状态变化都能追查；照片保存本地并可回看。"""
import io

from .conftest import (
    Api, DISPATCHER, REVIEWER, OP_LI, SEG_R101, VEH_X101,
)


def test_full_lifecycle_is_traceable(client):
    disp = Api(client).login(DISPATCHER)
    op = Api(client).login(OP_LI)
    rev = Api(client).login(REVIEWER)

    d = disp.post("/api/dispatches", json={
        "segment_id": SEG_R101, "vehicle_id": VEH_X101}).json()["id"]
    op.post("/api/work-records", json={
        "dispatch_id": d, "salt_kg": 500, "pos_x": 0.3, "pos_y": 0.22,
        "client_token": "t1"})
    op.post("/api/dispatches/complete", json={"dispatch_id": d})
    rev.post("/api/reviews", json={
        "segment_id": SEG_R101, "snow_cleared": True, "surface_safe": True,
        "note": "达标"})

    timeline = disp.get(f"/api/segments/{SEG_R101}/timeline").json()
    # 关键状态迁移链完整可查
    seg_transitions = [
        (e["from_status"], e["to_status"])
        for e in timeline if e["entity_type"] == "segment"
    ]
    assert ("untreated", "salted") in seg_transitions
    assert ("salted", "in_review") in seg_transitions
    assert ("in_review", "open") in seg_transitions

    # 每条都有操作人与时间
    for e in timeline:
        assert e["actor_name"]
        assert e["created_at"]

    actions = {e["action"] for e in timeline}
    assert {"dispatch_created", "uploaded", "submit_review", "review_passed"} <= actions


def test_photo_upload_saved_locally_and_served(client, tmp_path, monkeypatch):
    disp = Api(client).login(DISPATCHER)
    op = Api(client).login(OP_LI)
    d = disp.post("/api/dispatches", json={
        "segment_id": SEG_R101, "vehicle_id": VEH_X101}).json()["id"]

    # 1x1 PNG
    png = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
        "890000000a49444154789c6360000002000154a24f5f0000000049454e44ae42"
        "6082")
    r = op.post_form("/api/work-records/photo", data={
        "dispatch_id": str(d), "salt_kg": "120",
        "pos_x": "0.4", "pos_y": "0.22", "client_token": "photo-1"},
        files={"photo": ("scene.jpg", io.BytesIO(png), "image/png")})
    assert r.status_code == 200, r.text
    rec = r.json()
    assert rec["photo_url"] == f"/api/photos/{rec['id']}"
    assert rec["salt_kg"] == 120

    # 照片文件已落地到本地 data/photos
    from app.config import PHOTO_DIR
    files = list(PHOTO_DIR.glob("*"))
    assert len(files) == 1

    # 带令牌可回看
    img = client.get(rec["photo_url"] + f"?token={op.token}")
    assert img.status_code == 200
    assert img.content == png
    assert img.headers["content-type"].startswith("image/")


def test_photo_requires_auth(client):
    r = client.get("/api/photos/1")
    assert r.status_code == 401


def test_photo_upload_duplicate_token_not_double_count(client):
    disp = Api(client).login(DISPATCHER)
    op = Api(client).login(OP_LI)
    d = disp.post("/api/dispatches", json={
        "segment_id": SEG_R101, "vehicle_id": VEH_X101}).json()["id"]
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 32
    args = dict(data={
        "dispatch_id": str(d), "salt_kg": "200",
        "pos_x": "0.4", "pos_y": "0.22", "client_token": "dup-p"},
        files={"photo": ("a.jpg", io.BytesIO(png), "image/png")})
    r1 = op.post_form("/api/work-records/photo", **args)
    r2 = op.post_form("/api/work-records/photo", **args)
    assert r1.json()["duplicate"] is False
    assert r2.json()["duplicate"] is True
    assert r2.json()["id"] == r1.json()["id"]
    seg = disp.get(f"/api/segments/{SEG_R101}/detail").json()
    assert seg["salt_total_kg"] == 200
    assert len(seg["dispatches"][0]["records"]) == 1
