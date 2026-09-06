import sys, os, socket, signal, atexit, sqlite3

sys.path.insert(0, os.path.dirname(__file__))
from db import init_db, DB_PATH
from seeding import seed_questions, seed_exam_questions, seed_knowledge_graph
from backup import backup_database
from maintenance import startup_maintenance

# ---- 启动初始化 ----
init_db()
startup_maintenance()            # 启动治理：清理过期管理员会话等（静默失败）
backup_database(tag='startup')   # 启动即备份一份（自动保留最近 20 份）
seed_questions()
seed_exam_questions()
seed_knowledge_graph()

hostname = socket.gethostname()
local_ip = socket.gethostbyname(hostname)
print(f"Database ready.")
print(f"Local access:  http://localhost:5000")
print(f"LAN access:    http://{local_ip}:5000")

from app import app
from logs import log_system
log_system('info', '服务启动', detail=f'LAN: http://{local_ip}:5000', source='startup')

# ---- 退出清理 ----
_shutting_down = False

def _cleanup_db():
    """退出时：WAL checkpoint + 关闭所有连接 + 清理临时文件"""
    global _shutting_down
    if _shutting_down:
        return
    _shutting_down = True
    print("\n[cleanup] 正在清理数据库...")
    try:
        # 强制 checkpoint：把 WAL 内容写回主文件
        conn = sqlite3.connect(DB_PATH)
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.close()
        # 删掉残留的 WAL 临时文件
        for ext in ('-wal', '-shm'):
            p = DB_PATH + ext
            if os.path.exists(p):
                os.remove(p)
        print("[cleanup] 数据库已安全关闭，临时文件已清理。")
    except Exception as e:
        print(f"[cleanup] 清理时出错（可忽略）: {e}")

def _handle_signal(signum, frame):
    """收到 Ctrl+C 或 kill 信号时触发清理"""
    print(f"\n[signal] 收到退出信号 (signal={signum})")
    _cleanup_db()
    sys.exit(0)

atexit.register(_cleanup_db)
signal.signal(signal.SIGINT, _handle_signal)   # Ctrl+C
signal.signal(signal.SIGTERM, _handle_signal)  # kill / 任务管理器结束

# ---- 启动服务 ----
try:
    from waitress import serve
    print("Using waitress (production WSGI server)")
    print("Press Ctrl+C to stop.")
    serve(app, host='0.0.0.0', port=5000, threads=4)
except ImportError:
    print("Using Flask dev server (install waitress for better performance)")
    print("Press Ctrl+C to stop.")
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=False)
