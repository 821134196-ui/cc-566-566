"""pytest 公共夹具：每个用例使用独立临时 SQLite 库并重置种子数据。"""
import os
import tempfile

import pytest

# 必须在导入应用模块前设置，config.database 在导入时据此建引擎
_TMP = tempfile.mkdtemp(prefix="snow_pytest_")
os.environ["SNOW_DATA_DIR"] = _TMP
os.environ["SNOW_DB_PATH"] = os.path.join(_TMP, "test.db")

from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.seed import init_db  # noqa: E402


@pytest.fixture()
def client():
    Base.metadata.drop_all(bind=engine)
    init_db(seed=True)
    with TestClient(app) as c:
        yield c


class Api:
    """带登录态的轻量客户端封装。"""

    def __init__(self, client):
        self.c = client
        self.token = None
        self.user = None

    def login(self, username: str, password: str = "123456"):
        r = self.c.post("/api/auth/login",
                        json={"username": username, "password": password})
        assert r.status_code == 200, r.text
        data = r.json()
        self.token = data["token"]
        self.user = data["user"]
        return self

    def _h(self, extra=None):
        h = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        if extra:
            h.update(extra)
        return h

    def get(self, path, **kw):
        return self.c.get(path, headers=self._h(kw.pop("headers", None)), **kw)

    def post(self, path, json=None, **kw):
        return self.c.post(path, json=json, headers=self._h(kw.pop("headers", None)), **kw)

    def post_form(self, path, data=None, files=None):
        h = self._h()
        # multipart 不要手动设 Content-Type，由 TestClient 生成 boundary
        return self.c.post(path, data=data, files=files, headers=h)


@pytest.fixture()
def api(client):
    return Api(client)


# 种子数据里的固定 id（见 app/seed.py）
DISPATCHER = "dispatcher"
REVIEWER = "reviewer"
MANAGER = "manager"
OP_LI = "li"      # X101（一级能力）
OP_CHEN = "chen"  # X201（二级能力），且兼复核身份
OP_SUN = "sun"    # X301（仅三级能力）

# 路段：id 1/2 一级，3/4/5 二级，6/7/8 三级
SEG_R101, SEG_R102 = 1, 2
SEG_R201, SEG_R202, SEG_R203 = 3, 4, 5
SEG_R301, SEG_R302, SEG_R303 = 6, 7, 8
VEH_X101, VEH_X102, VEH_X201, VEH_X301 = 1, 2, 3, 4
