#!/usr/bin/env bash
# 城市道路积雪撒盐与路段复核系统 —— 一条命令本地启动
#
# 用法：
#   ./run.sh            启动服务（首次运行自动安装依赖、初始化数据库）
#   ./run.sh reset      清空本地数据并重新初始化（演示账号与模拟路网）
#   ./run.sh test       运行后端验证测试
#
# 启动后访问： http://127.0.0.1:8000
set -euo pipefail

cd "$(dirname "$0")"
BACKEND=backend
DEPS=$BACKEND/.pydeps
DATA_DIR=${SNOW_DATA_DIR:-"$PWD/data"}
export SNOW_DATA_DIR="$DATA_DIR"
export PYTHONPATH="$DEPS:$BACKEND${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONUNBUFFERED=1
PORT=${PORT:-8000}

# 1) 确保 pip 可用（兼容无 python3-venv / 无系统 pip 的精简环境）
if ! python3 -c "import pip" >/dev/null 2>&1; then
  echo "[run.sh] 首次运行：正在引导 pip ..."
  if [ ! -f /tmp/get-pip.py ]; then
    curl -sS https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py
  fi
  python3 /tmp/get-pip.py --user --break-system-packages >/dev/null
fi

# 2) 安装依赖到项目本地 .pydeps（不污染系统环境，无需 venv）
if [ ! -f "$DEPS/.install_ok" ] || [ "$BACKEND/requirements.txt" -nt "$DEPS/.install_ok" ]; then
  echo "[run.sh] 安装 Python 依赖到 $DEPS ..."
  python3 -m pip install -q --upgrade --target "$DEPS" -r "$BACKEND/requirements.txt"
  touch "$DEPS/.install_ok"
fi

# 3) 子命令
case "${1:-serve}" in
  reset)
    echo "[run.sh] 清空 $DATA_DIR 并重新初始化 ..."
    rm -rf "$DATA_DIR"
    mkdir -p "$DATA_DIR"
    python3 -c "from app.seed import init_db; init_db(); print('数据库已初始化')"
    echo "完成。再次运行 ./run.sh 启动。"
    ;;
  test)
    export SNOW_DB_PATH="$DATA_DIR/pytest_tmp.db"
    python3 -m pytest "$BACKEND/tests" -v "${@:2}"
    ;;
  serve|"")
    mkdir -p "$DATA_DIR"
    echo "────────────────────────────────────────────────────────"
    echo " 城市道路积雪撒盐与路段复核系统"
    echo " 访问地址 : http://127.0.0.1:${PORT}"
    echo " 演示账号 : dispatcher / li / reviewer / manager / chen（密码 123456）"
    echo " 数据目录 : $DATA_DIR （SQLite + 现场照片）"
    echo " 停止服务 : Ctrl+C"
    echo "────────────────────────────────────────────────────────"
    exec python3 -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT" \
      --app-dir "$BACKEND"
    ;;
  *)
    echo "未知命令：$1（可用：serve / reset / test）"; exit 1;;
esac
