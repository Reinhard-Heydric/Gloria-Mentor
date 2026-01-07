import json, subprocess, asyncio, aiohttp, socket, time
from pathlib import Path
from typing import Dict, Optional
from py.get_setting import EXT_DIR

PORT_RANGE = (3100, 13999)   # 给扩展自动分配的端口池

class NodeExtension:
    def __init__(self, ext_id: str):
        self.ext_id   = ext_id
        self.proc: Optional[asyncio.subprocess.Process] = None
        self.port: Optional[int] = None
        self.root     = Path(EXT_DIR) / ext_id
        self.pkg      = json.loads((self.root / "package.json").read_text())

    async def start(self) -> int:
        if self.proc and self.proc.returncode is None:
            return self.port

        # 0. 快速判断：node_modules 存在且比 package.json 新
        pkg_file = self.root / "package.json"
        nm_folder = self.root / "node_modules"
        if nm_folder.is_dir() and nm_folder.stat().st_mtime >= pkg_file.stat().st_mtime:
            # 已安装且没改动过，跳过
            print(f"[{self.ext_id}] node_modules 已存在，跳过 npm install")
        else:
            # 1. 真正安装
            print(f"[{self.ext_id}] 首次/依赖变更，执行 npm install")
            proc = await asyncio.create_subprocess_exec(
                "npm", "install", "--production",
                cwd=self.root, stdout=asyncio.subprocess.DEVNULL
            )
            await proc.wait()
            # 安装完成后把 node_modules 时间戳刷到最新，避免下次重复
            nm_folder.touch(exist_ok=True)
        # 2. 选端口
        want = self.pkg.get("nodePort", 0)
        self.port = want if want else _free_port()
        # 3. 起进程
        self.proc = await asyncio.create_subprocess_exec(
            "node", "index.js", str(self.port),
            cwd=self.root,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT
        )
        # 4. 等健康
        await _wait_port(self.port)
        return self.port

    async def stop(self):
        if self.proc:
            self.proc.terminate()
            await self.proc.wait()
            self.proc = None

# ---------- 工具 ----------
def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("", 0))
        return s.getsockname()[1]

async def _wait_port(port: int, timeout=10):
    for _ in range(timeout * 10):
        try:
            _, w = await asyncio.wait_for(asyncio.open_connection("127.0.0.1", port), 1)
            w.close()
            return
        except:
            await asyncio.sleep(0.1)
    raise RuntimeError("端口未就绪")

# ---------- 全局管理器 ----------
class NodeManager:
    def __init__(self):
        self.exts: Dict[str, NodeExtension] = {}

    async def start(self, ext_id: str) -> int:
        if ext_id not in self.exts:
            self.exts[ext_id] = NodeExtension(ext_id)
        return await self.exts[ext_id].start()

    async def stop(self, ext_id: str):
        if ext_id in self.exts:
            await self.exts[ext_id].stop()
            del self.exts[ext_id]

node_mgr = NodeManager()