#!/bin/bash
# ==========================================
# AI 游玩日志生成系统 — 一键启动
# 启动后端 + ngrok 公网穿透 + 防 Mac 睡眠
# ==========================================

echo "========================================"
echo "  AI 游玩日志生成系统"
echo "  后端启动 + 公网穿透 + 防睡眠"
echo "========================================"
echo ""

# 进入脚本所在目录
cd "$(dirname "$0")"

# ---- 1. 防止 Mac 睡眠 ----
echo "🔋 防止 Mac 睡眠..."
caffeinate -dimsu &
CAFFEINATE_PID=$!

# ---- 2. 启动后端 ----
echo "🚀 启动 FastAPI 后端..."
cd backend
if [ -d ".venv" ]; then
  source .venv/bin/activate
fi
pip install -r requirements.txt -q 2>/dev/null
uvicorn app:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!
sleep 3

LAN_IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo "未知")
echo "   本地访问: http://127.0.0.1:8000"
echo "   局域网访问: http://${LAN_IP}:8000"

# ---- 3. 启动 ngrok ----
echo ""
echo "🌐 启动 ngrok 公网穿透..."
if ! command -v ngrok &> /dev/null; then
  echo "   ❌ ngrok 未安装！请在终端执行: brew install ngrok"
  echo "   然后重新双击本脚本。"
else
  ngrok http 8000 --log=stdout &
  NGROK_PID=$!
  sleep 3

  # 获取 ngrok 公网地址
  NGROK_URL=$(curl -s http://127.0.0.1:4040/api/tunnels 2>/dev/null | python3 -c "
import sys,json
try:
  tunnels = json.load(sys.stdin).get('tunnels', [])
  url = next((t['public_url'] for t in tunnels if t['public_url'].startswith('https')), '')
  print(url)
except: pass
" 2>/dev/null)
fi

echo ""
echo "========================================"
echo "  ✅ 启动完成"
echo "========================================"
echo ""
echo "  本地:     http://127.0.0.1:8000"
echo "  局域网:   http://${LAN_IP}:8000"
if [ -n "$NGROK_URL" ]; then
  echo "  🌍 公网:   $NGROK_URL"
  echo ""
  echo "  📱 把公网地址发给朋友，手机浏览器打开即可使用"
else
  echo "  ⚠️  公网地址获取中，查看上方 ngrok 输出"
fi
echo ""
echo "  按 Ctrl+C 停止所有服务"
echo "========================================"

# 保持运行，Ctrl+C 时清理
cleanup() {
  echo ""
  echo "停止所有服务..."
  kill $BACKEND_PID 2>/dev/null
  kill $NGROK_PID 2>/dev/null
  kill $CAFFEINATE_PID 2>/dev/null
  echo "已停止。"
}
trap cleanup EXIT INT TERM
wait
