import json
import os
import sys
import time
import aiosqlite
from pathlib import Path
HOST = None
PORT = None
def configure_host_port(host, port):
    global HOST, PORT
    HOST = host
    PORT = port
def get_host():
    return HOST or "127.0.0.1"  # 提供默认值
def get_port():
    return PORT or 3456

def in_docker():
    def check_cgroup():
        try:
            with open('/proc/1/cgroup', 'rt',encoding='utf-8') as ifh:
                for line in ifh:
                    if 'docker' in line or 'container' in line:
                        return True
        except FileNotFoundError:
            pass
        return False

    def check_dockerenv():
        try:
            with open('/.dockerenv', 'rt',encoding='utf-8') as ifh:
                # 文件存在即表示是在Docker容器中
                return True
        except FileNotFoundError:
            return False

    def check_proc_self_status():
        try:
            with open('/proc/self/status', 'rt',encoding='utf-8') as ifh:
                for line in ifh:
                    if line.startswith('Context') and 'container=docker' in line:
                        return True
        except FileNotFoundError:
            pass
        return False
    
    return any([check_cgroup(), check_dockerenv(), check_proc_self_status()])

def get_base_path():
    """判断当前是开发环境还是打包环境，返回基础路径"""
    if getattr(sys, 'frozen', False):
        # 打包后，资源在 sys._MEIPASS 指向的临时目录
        return sys._MEIPASS
    else:
        # 开发环境使用当前工作目录
        return os.path.abspath(".")
    
# 在get_setting.py开头添加
from appdirs import user_data_dir
# 替换原有的base_path定义
APP_NAME = "Super-Agent-Party"  # 替换为你的应用名称

if in_docker():
    USER_DATA_DIR = '/app/data'
else:
    USER_DATA_DIR = user_data_dir(APP_NAME, roaming=True)

os.makedirs(USER_DATA_DIR, exist_ok=True)

LOG_DIR = os.path.join(USER_DATA_DIR, 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

MEMORY_CACHE_DIR = os.path.join(USER_DATA_DIR, 'memory_cache')
os.makedirs(MEMORY_CACHE_DIR, exist_ok=True)

UPLOAD_FILES_DIR = os.path.join(USER_DATA_DIR, 'uploaded_files')
os.makedirs(UPLOAD_FILES_DIR, exist_ok=True)

TOOL_TEMP_DIR = os.path.join(USER_DATA_DIR, 'tool_temp')
os.makedirs(TOOL_TEMP_DIR, exist_ok=True)

# 删除TOOL_TEMP_DIR中超过一周未修改的文件
for filename in os.listdir(TOOL_TEMP_DIR):
    file_path = os.path.join(TOOL_TEMP_DIR, filename)
    if os.path.isfile(file_path):
        if time.time() - os.path.getmtime(file_path) > 7 * 24 * 60 * 60:
            os.remove(file_path)
            

AGENT_DIR = os.path.join(USER_DATA_DIR, 'agents')
os.makedirs(AGENT_DIR, exist_ok=True)

KB_DIR = os.path.join(USER_DATA_DIR, 'kb')
os.makedirs(KB_DIR, exist_ok=True)

# 修改SETTINGS_FILE路径
SETTINGS_FILE = os.path.join(USER_DATA_DIR, 'settings.json')

base_path = get_base_path()
CONFIG_BASE_PATH = os.path.join(base_path, 'config')
os.makedirs(CONFIG_BASE_PATH, exist_ok=True)
DEFAULT_VRM_DIR = os.path.join(base_path, 'vrm')
DEFAULT_ASR_DIR = os.path.join(base_path, 'vrm', 'asr')
os.makedirs(DEFAULT_ASR_DIR, exist_ok=True)
STATIC_DIR = os.path.join(base_path, "static")
EXT_DIR = os.path.join(base_path, "static", "ext")
SETTINGS_TEMPLATE_FILE = os.path.join(CONFIG_BASE_PATH, 'settings_template.json')
with open(SETTINGS_TEMPLATE_FILE, 'r', encoding='utf-8') as f:
    default_settings = json.load(f)

# 修改数据库路径定义
DATABASE_PATH = os.path.join(USER_DATA_DIR, 'super_agent_party.db')
# 添加数据库初始化函数
async def init_db():
    Path(USER_DATA_DIR).mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY,
                data TEXT NOT NULL
            )
        ''')
        await db.commit()
# 修改 load_settings 函数
async def load_settings():
    await init_db()
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute('SELECT data FROM settings WHERE id = 1') as cursor:
            row = await cursor.fetchone()
            if row:
                settings = json.loads(row[0])
                # 合并默认设置（保持原有逻辑）
                def merge_defaults(default, target):
                    for key, value in default.items():
                        if key not in target:
                            target[key] = value
                        elif isinstance(value, dict):
                            merge_defaults(value, target[key])
                merge_defaults(default_settings, settings)
                return settings
            else:
                # 如果in_docker()返回True，则修改默认配置
                if in_docker():
                    default_settings["isdocker"] = True
                # 插入默认配置
                await save_settings(default_settings)
                return default_settings.copy()
# 修改 save_settings 函数
async def save_settings(settings):
    data = json.dumps(settings, ensure_ascii=False, indent=2)
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute('INSERT OR REPLACE INTO settings (id, data) VALUES (1, ?)', (data,))
        await db.commit()