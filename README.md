# 城市道路积雪撒盐与路段复核系统

降雪天气下的清雪作业闭环：**调度员按道路等级派车 → 车辆逐路段回传作业（时间 / 融雪剂 / 现场照片 / 定位）→ 撒盐完成进入待复核 → 复核员确认达标后路段开放 → 管理人员在一张图上掌握进度**。

- 后端：Python 3.11 + FastAPI + SQLAlchemy 2 + SQLite
- 前端：Vue 3（无构建、本地 vendored，离线可用），由 FastAPI 静态托管
- 地图与车辆位置：模拟接口（SVG 路网 + 确定性模拟 GPS，每 5 秒刷新）
- 照片：保存在本地 `data/photos/`

## 一条命令启动

```bash
./run.sh
```

首次运行会自动引导 pip、把依赖安装到项目本地 `backend/.pydeps`（不污染系统环境、无需 venv）、初始化 SQLite，然后启动服务。

启动后打开 **http://127.0.0.1:8000**

其他命令：

```bash
./run.sh test     # 运行 24 项后端验证测试
./run.sh reset    # 清空 data/ 并重新初始化演示数据
PORT=8080 ./run.sh
```

> 无 bash 时也可手动：`PYTHONPATH=backend/.pydeps:backend python3 -m uvicorn app.main:app --app-dir backend`

## 演示账号（密码均为 123456）

| 账号 | 角色 | 用途 |
|---|---|---|
| `dispatcher` 刁调度 | 调度员 | 按道路等级派车 |
| `li` 李作业 | 作业人员 | X101 撒盐车（可上一级路），回传作业、报故障、申请复核 |
| `chen` 陈兼岗 | 作业人员 + 复核员 | 专门验证「作业人员不能复核自己路段」 |
| `reviewer` 王复核 | 复核员 | 独立第三方，确认达标后开放路段 |
| `manager` 张管理 | 管理人员 | 只看地图与进度，无操作权限 |

推荐走一遍：`dispatcher` 派车到「解放路一段」→ `li` 回传 1~2 次作业（可传照片）→ 点「撒盐完成·申请复核」→ `reviewer` 勾选两项达标并开放。

## 路段状态机（地图颜色）

```
未清理 untreated ──首次作业回传──▶ 已撒盐 salted ──撒盐完成──▶ 待复核 in_review
                                       ▲                            │
                                       │ 复核驳回（需补盐）          │ 复核通过（积雪+路面均达标）
                                       └────────────────────────────┴──▶ 已开放 open
```

- ⚪ 灰色虚线：未清理　🟠 琥珀：已撒盐/待补盐　🔵 蓝色流动：待复核　🟢 绿色：已开放
- 补盐走**新派车单**，路段回到 `salted → in_review`，需要复核员再次确认。

## 关键业务规则（均已被测试锁定）

1. **追加不覆盖**：同一路段再次撒盐生成新的派车单与新的作业记录，首次记录原样保留，融雪剂用量按记录累加。
2. **重复回传不计量**：相同 `client_token`（网络重试），或同一派车单内在时间窗内「定位网格相同 + 用量相同（±0.5kg）」的回传，判定为重复 → 返回原记录并标 `duplicate=true`，**不写库、不加盐量**，但写审计 `duplicate_upload_ignored`。
3. **复核权限分离**：只有复核员能提交开放结论；调度员、作业人员、管理人员均 403。**凡是在该路段上传过作业记录的人，即使同时具备复核身份也不能签发本路段**（陈兼岗登录可验证）。
4. **未复核绝不开放**：`open` 只能由「待复核 + 两项达标 + 复核通过」到达；没有作业记录不能申请复核；故障未处理不能完成撒盐。
5. **故障中断可追溯**：车辆故障 → 派车单中断、车辆置故障、不能完成/再派；必须登记故障原因与后续安排并处理后才能恢复。
6. **全程可追查**：每次状态变化写 `audit_logs`（操作人、前后状态、说明、时间），路段详情页时间线合并展示派车 / 作业 / 故障 / 复核。
7. **按道路等级派车**：车辆有可承担最高等级（一级车可支援支路，三级车不能上主干道），后端强校验。

## 验证测试

```bash
./run.sh test
```

覆盖（24 项）：

- `test_dedup.py`：同 token 重复回传、无 token 同定位同用量去重、不同定位算新作业、重复事件入审计
- `test_supplement.py`：驳回保留历史、补盐追加新记录不累加覆盖、补盐后通过复核才开放
- `test_review_rules.py`：双身份作业员不能复核自己路段、独立复核员可通过、其他角色 403、未申请复核不能复核、未通过不开放、无作业记录不能完成
- `test_dispatch_breakdown.py`：等级派车约束、仅调度员可派车、故障阻断完成与再派、故障恢复后放行、不能代报他人车辆故障
- `test_trace_photo.py`：完整状态链可追查、照片落盘与鉴权回看、照片回传重复不计量

## 主要接口

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/auth/login` | 登录换 token |
| GET | `/api/map` | 地图：路段状态 + 车辆实时（模拟）位置 |
| POST | `/api/dispatches` | 调度员派车（等级校验） |
| POST | `/api/work-records` | 作业回传（JSON，幂等去重） |
| POST | `/api/work-records/photo` | 作业回传（multipart，照片存本地） |
| POST | `/api/dispatches/complete` | 撒盐完成 → 待复核 |
| POST | `/api/breakdowns` / `/{id}/resolve` | 故障中断登记 / 后续处理 |
| POST | `/api/reviews` | 复核结论（通过开放 / 驳回补盐，含回避校验） |
| GET | `/api/segments/{id}/detail` `/timeline` | 路段全量历史与审计轨迹 |
| GET | `/api/photos/{record_id}` | 现场照片（需登录） |

交互式文档：服务启动后访问 `http://127.0.0.1:8000/docs`。

## 目录结构

```
.
├── run.sh                  # 一键启动 / 测试 / 重置
├── backend/
│   ├── requirements.txt
│   ├── .pydeps/            # 本地依赖（run.sh 自动生成）
│   ├── app/
│   │   ├── main.py         # FastAPI 入口，托管前端
│   │   ├── models.py       # 用户/车辆/路段/派车/作业/故障/复核/审计
│   │   ├── routers/        # auth meta dispatch work breakdown review trace photo
│   │   ├── security.py     # 令牌认证与角色控制
│   │   ├── audit.py        # 统一审计写入
│   │   └── seed.py         # 演示路网 / 车辆 / 账号
│   └── tests/              # pytest 24 项
├── frontend/
│   ├── index.html          # 登录 + 地图 + 四角色工作台 + 详情时间线
│   ├── app.js styles.css
│   └── vendor/vue.global.prod.js
└── data/                   # snow.db 与 photos/（运行后生成）
```

> 说明：本系统为本地演示用途，密码明文存储、令牌为轻量 HMAC，请勿直接用于生产。
