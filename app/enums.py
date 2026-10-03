"""系统中的角色、路段 / 车辆 / 派车单状态常量。"""

# 用户角色（一个用户可兼有多个角色，逗号分隔存储）
ROLE_DISPATCHER = "dispatcher"  # 清雪调度员：派车
ROLE_WORKER = "worker"          # 作业人员：随车回传作业记录
ROLE_REVIEWER = "reviewer"      # 复核员：签发路段开放结论
ROLE_ADMIN = "admin"            # 管理人员：查看全局进度与审计

# 路段开放流程中的三个主状态（地图据此三色区分）
ROAD_UNCLEARED = "uncleared"            # 未清理（含作业中）
ROAD_PENDING_REVIEW = "pending_review"  # 撒盐完成，待复核
ROAD_OPEN = "open"                      # 复核达标，已开放通行
ROAD_STATUSES = (ROAD_UNCLEARED, ROAD_PENDING_REVIEW, ROAD_OPEN)

ROAD_STATUS_LABEL = {
    ROAD_UNCLEARED: "未清理",
    ROAD_PENDING_REVIEW: "待复核",
    ROAD_OPEN: "已开放",
}

# 道路等级（调度员按等级派车，等级决定优先顺序）
GRADE_ARTERIAL = "arterial"    # 主干路
GRADE_SECONDARY = "secondary"  # 次干路
GRADE_BRANCH = "branch"        # 支路
GRADE_LABEL = {
    GRADE_ARTERIAL: "主干路",
    GRADE_SECONDARY: "次干路",
    GRADE_BRANCH: "支路",
}

# 车辆状态
VEHICLE_IDLE = "idle"            # 待命
VEHICLE_WORKING = "working"      # 作业中
VEHICLE_BREAKDOWN = "breakdown"  # 故障
VEHICLE_STATUSES = (VEHICLE_IDLE, VEHICLE_WORKING, VEHICLE_BREAKDOWN)

# 派车单状态
ASSIGN_DISPATCHED = "dispatched"    # 已派车，尚未回传
ASSIGN_IN_PROGRESS = "in_progress"  # 作业中
ASSIGN_INTERRUPTED = "interrupted"  # 故障中断
ASSIGN_COMPLETED = "completed"      # 撒盐完成，已进入待复核
ASSIGN_STATUSES = (
    ASSIGN_DISPATCHED,
    ASSIGN_IN_PROGRESS,
    ASSIGN_INTERRUPTED,
    ASSIGN_COMPLETED,
)

# 作业回传去重：同一派车单下坐标完全一致、作业时间相差不超过该秒数，视为重复定位
DEDUP_WINDOW_SECONDS = 60
