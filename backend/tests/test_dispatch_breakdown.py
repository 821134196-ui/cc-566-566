"""验证按道路等级派车、车辆故障中断与后续安排。"""
from .conftest import (
    Api, DISPATCHER, OP_LI, OP_SUN, OP_CHEN,
    SEG_R101, SEG_R201, SEG_R301,
    VEH_X101, VEH_X201, VEH_X301,
)


def test_level3_vehicle_cannot_serve_level1_road(client):
    disp = Api(client).login(DISPATCHER)
    r = disp.post("/api/dispatches", json={
        "segment_id": SEG_R101, "vehicle_id": VEH_X301})  # 三级车上一级路
    assert r.status_code == 400


def test_level2_vehicle_cannot_serve_level1_but_can_level2(client):
    disp = Api(client).login(DISPATCHER)
    r = disp.post("/api/dispatches", json={
        "segment_id": SEG_R101, "vehicle_id": VEH_X201})  # 二级车上一级路
    assert r.status_code == 400

    r = disp.post("/api/dispatches", json={
        "segment_id": SEG_R201, "vehicle_id": VEH_X201})  # 二级车上二级路
    assert r.status_code == 200, r.text


def test_high_capability_vehicle_can_serve_lower_level_road(client):
    disp = Api(client).login(DISPATCHER)
    r = disp.post("/api/dispatches", json={
        "segment_id": SEG_R301, "vehicle_id": VEH_X101})  # 一级车支援支路
    assert r.status_code == 200


def test_only_dispatcher_can_dispatch(client):
    op = Api(client).login(OP_LI)
    r = op.post("/api/dispatches", json={
        "segment_id": SEG_R101, "vehicle_id": VEH_X101})
    assert r.status_code == 403


def test_breakdown_blocks_completion_until_resolved(client):
    disp = Api(client).login(DISPATCHER)
    op = Api(client).login(OP_LI)

    d = disp.post("/api/dispatches", json={
        "segment_id": SEG_R101, "vehicle_id": VEH_X101}).json()["id"]
    op.post("/api/work-records", json={
        "dispatch_id": d, "salt_kg": 500, "pos_x": 0.3, "pos_y": 0.22,
        "client_token": "t1"})

    # 中途故障
    r = op.post("/api/breakdowns", json={
        "dispatch_id": d, "reason": "撒布机液压故障",
        "follow_up": "通知维修组抢修，预计40分钟；备用车 X102 待命"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "interrupted"

    # 未处理的故障不允许完成撒盐
    r = op.post("/api/dispatches/complete", json={"dispatch_id": d})
    assert r.status_code == 409

    # 车辆进入故障状态，不能再被派
    r = disp.post("/api/dispatches", json={
        "segment_id": SEG_R301, "vehicle_id": VEH_X101})
    assert r.status_code == 409

    # 记录后续安排并解除
    r = op.post(f"/api/breakdowns/1/resolve", json={
        "follow_up_result": "现场更换液压油管，试车正常，继续剩余路段撒盐"})
    assert r.status_code == 200, r.text

    # 恢复后可以完成
    r = op.post("/api/dispatches/complete", json={"dispatch_id": d})
    assert r.status_code == 200
    seg = disp.get(f"/api/segments/{SEG_R101}/detail").json()
    assert seg["status"] == "in_review"

    # 故障与后续安排都挂在派车单上可查
    d_detail = disp.get(f"/api/dispatches/{d}").json()
    assert len(d_detail["breakdowns"]) == 1
    assert "液压" in d_detail["breakdowns"][0]["reason"]
    assert d_detail["breakdowns"][0]["status"] == "resolved"


def test_operator_cannot_report_others_vehicle_breakdown(client):
    disp = Api(client).login(DISPATCHER)
    other = Api(client).login(OP_SUN)   # sun 是 X301 的作业员
    d = disp.post("/api/dispatches", json={
        "segment_id": SEG_R101, "vehicle_id": VEH_X101}).json()["id"]
    r = other.post("/api/breakdowns", json={
        "dispatch_id": d, "reason": "x", "follow_up": "y"})
    assert r.status_code == 403
