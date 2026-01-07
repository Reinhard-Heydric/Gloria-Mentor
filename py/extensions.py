# extensions.py
import stat
import shutil
import tempfile
import subprocess
from pathlib import Path
from urllib.parse import urlparse
import httpx
from fastapi import APIRouter, HTTPException,BackgroundTasks, Response, Request
from pydantic import BaseModel
from typing import List, Optional
import os
import json
from fastapi import UploadFile, File
from py.get_setting import EXT_DIR
router = APIRouter(prefix="/api/extensions", tags=["extensions"])

class Extension(BaseModel):
    id: str
    name: str
    description: str = "无描述"
    version: str = "1.0.0"
    author: str = "未知"
    systemPrompt: str = ""
    repository: str = ""
    backupRepository: Optional[str] = ""
    category: str = ""
    transparent: bool = False
    width: int = 800
    height: int = 600

class ExtensionsResponse(BaseModel):
    extensions: List[Extension]

@router.get("/list", response_model=ExtensionsResponse)
async def list_extensions():
    """获取所有可用的扩展列表"""
    try:
        extensions_dir = EXT_DIR
        
        # 确保扩展目录存在
        if not os.path.exists(extensions_dir):
            os.makedirs(extensions_dir, exist_ok=True)
            return ExtensionsResponse(extensions=[])
        
        # 读取扩展目录
        extensions = []
        for dir_name in os.listdir(extensions_dir):
            dir_path = os.path.join(extensions_dir, dir_name)
            if os.path.isdir(dir_path):
                ext_id = dir_name
                index_path = os.path.join(dir_path, "index.html")
                
                # 检查index.html是否存在
                if os.path.exists(index_path):
                    # 尝试读取扩展的package.json获取元数据
                    package_path = os.path.join(dir_path, "package.json")
                    if os.path.exists(package_path):
                        try:
                            with open(package_path, 'r', encoding='utf-8') as f:
                                package_data = json.load(f)
                                
                            extensions.append(Extension(
                                id=ext_id,
                                name=package_data.get("name", ext_id),
                                description=package_data.get("description", "无描述"),
                                version=package_data.get("version", "1.0.0"),
                                author=package_data.get("author", "未知"),
                                systemPrompt = package_data.get("systemPrompt", ""),
                                repository = package_data.get("repository", ""),
                                category = package_data.get("category", ""),
                                transparent = package_data.get("transparent", False),
                                width = package_data.get("width", 800),
                                height = package_data.get("height", 600)
                            ))
                        except json.JSONDecodeError:
                            # package.json解析失败，使用默认值
                            extensions.append(Extension(
                                id=ext_id,
                                name=ext_id
                            ))
                    else:
                        # 没有package.json，使用默认值
                        extensions.append(Extension(
                            id=ext_id,
                            name=ext_id
                        ))
        
        return ExtensionsResponse(extensions=extensions)
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取扩展列表失败: {str(e)}")


def _remove_readonly(func, path, exc_info):
    """onexc 回调：如果失败就改权限再删一次"""
    os.chmod(path, stat.S_IWRITE)
    func(path)

def robust_rmtree(target: Path):
    target = Path(target)
    if not target.exists():
        return
    # Python ≥3.12 用 onexc；旧版本用 onerror 即可
    kwargs = {"onexc": _remove_readonly} if hasattr(shutil, "rmtree") and "onexc" in shutil.rmtree.__annotations__ else {"onerror": _remove_readonly}
    shutil.rmtree(target, **kwargs)

# ------------------ 删除扩展 ------------------
@router.delete("/{ext_id}", status_code=204)
async def delete_extension(ext_id: str):
    target = Path(EXT_DIR) / ext_id
    if not target.exists():
        raise HTTPException(status_code=404, detail="扩展不存在")
    try:
        robust_rmtree(target)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除失败: {e}")
    return

# ------------------ GitHub 安装 ------------------
class GitHubInstallRequest(BaseModel):
    url: str          # 支持 https://github.com/owner/repo 或 直接 zip 下载地址

def _run_bg_install(repo_url: str, ext_id: str):
    """
    repo_url 可能是
      1) GitHub 仓库首页  https://github.com/owner/repo
      2) GitHub zip 包地址 https://github.com/owner/repo/archive/refs/heads/main.zip
      3) Gitee 仓库首页   https://gitee.com/owner/repo
      4) Gitee zip 包地址 …
    如果 ext_dir 里已经有 package.json 并且写了 backupRepository，
    就把主仓库和备用仓库组成一个 list，顺序尝试，成功即跳出。
    """
    target = Path(EXT_DIR) / ext_id
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp())

    # --------------- 组装“主 + 备” 地址列表 ---------------
    # 先读本地 package.json（如果已存在，可能是更新场景）
    pkg_file = target / "package.json"
    backup: str = ""
    if pkg_file.exists():
        try:
            backup = json.loads(pkg_file.read_text(encoding="utf-8")).get("backupRepository", "")
        except Exception:
            pass

    urls: List[str] = []
    # 主仓库
    if repo_url.strip():
        urls.append(repo_url.strip().rstrip("/"))
    # 备用仓库
    if backup.strip():
        urls.append(backup.strip().rstrip("/"))

    if not urls:
        raise RuntimeError("没有任何可用仓库地址")

    # --------------- 顺序尝试克隆 / 下载 ---------------
    last_err: Exception | None = None
    for url in urls:
        try:
            _do_single_install(url, temp_dir, target)
            # 成功就直接返回，外层不会走到 except
            return
        except Exception as e:
            last_err = e
            continue

    # 所有地址都失败
    if target.exists():
        robust_rmtree(target)
    shutil.rmtree(temp_dir, ignore_errors=True)
    raise RuntimeError(f"主/备仓库均安装失败：{last_err}")


def _do_single_install(url: str, temp_dir: Path, target: Path):
    """真正执行一次下载或克隆"""
    # 下载 zip 包
    if url.endswith(".zip"):
        zip_path = temp_dir / "repo.zip"
        with httpx.stream("GET", url, follow_redirects=True) as resp:
            resp.raise_for_status()
            with open(zip_path, "wb") as f:
                for chunk in resp.iter_bytes():
                    f.write(chunk)
        shutil.unpack_archive(zip_path, temp_dir)
        inner = next(d for d in temp_dir.iterdir() if d.is_dir() and d.name != "repo.zip")
        if inner.exists():
            shutil.move(str(inner), str(target))
    else:
        # git clone
        clone_dir = temp_dir / "repo"
        # 删除url中的 .git和/
        url = url.rstrip("/").rstrip(".git")
        subprocess.run(
            ["git", "clone", f"{url}.git", str(clone_dir)],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        shutil.move(str(clone_dir), str(target))


@router.post("/install-from-github")
async def install_from_github(
    req: GitHubInstallRequest, background: BackgroundTasks
):
    """
    1. 解析仓库名作为 ext_id
    2. 如果已存在直接 409
    3. 后台任务克隆/下载
    4. 立即返回 202，前端轮询或 websocket 通知可后续扩展
    """
    parse = urlparse(req.url)
    if not parse.netloc or "github" not in parse.netloc:
        raise HTTPException(status_code=400, detail="仅支持 GitHub 地址")
    # 取 owner/repo 作为 ext_id
    path_parts = parse.path.strip("/").split("/")
    if len(path_parts) < 2:
        raise HTTPException(status_code=400, detail="URL 格式错误")
    ext_id = f"{path_parts[0]}_{path_parts[1]}"
    target = Path(EXT_DIR) / ext_id
    if target.exists():
        raise HTTPException(status_code=409, detail="扩展已存在")
    # 后台执行
    background.add_task(_run_bg_install, req.url, ext_id)
    return {"ext_id": ext_id, "status": "installing"}

def find_root_dir(temp_path: Path) -> Path:
    """
    如果 zip 解压后只有 1 个一级目录，并且该目录下有 index.html，
    就认为这一层是多余的，返回其子目录；否则返回原路径。
    """
    entries = [p for p in temp_path.iterdir() if p.is_dir()]
    if len(entries) == 1 and (entries[0] / "index.html").exists():
        return entries[0]
    return temp_path

@router.post("/upload-zip")
async def upload_zip(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="仅支持 zip 文件")
    ext_id = Path(file.filename).stem
    target = Path(EXT_DIR) / ext_id
    if target.exists():
        raise HTTPException(status_code=409, detail="扩展已存在")

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        # 1. 保存上传的 zip
        zip_path = tmp / "up.zip"
        with zip_path.open("wb") as f:
            shutil.copyfileobj(file.file, f)
        # 2. 解压到 tmp/unpack
        unpack = tmp / "unpack"
        shutil.unpack_archive(zip_path, unpack)
        # 3. 去掉可能的中间目录
        real_root = find_root_dir(unpack)
        # 4. 移动到最终位置
        target.mkdir(parents=True, exist_ok=True)
        for item in real_root.iterdir():
            shutil.move(str(item), str(target))

    return {"ext_id": ext_id, "status": "ok"}

class RemotePluginItem(BaseModel):
    id : str 
    name: str
    description: str
    author: str
    version: str
    category: str = "Unknown"
    repository: str          # 唯一标识
    installed: bool = False  # 后端自动填充

class RemotePluginList(BaseModel):
    plugins: List[RemotePluginItem]

# 把路由函数整个替换成下面这段即可
@router.get("/remote-list", response_model=RemotePluginList)
async def remote_plugin_list():
    github_raw = (
        "https://raw.githubusercontent.com/"
        "super-agent-party/super-agent-party.github.io/"
        "main/plugins.json"
    )
    gitee_raw = (
        "https://gitee.com/super-agent-party/super-agent-party.github.io/"
        "raw/main/plugins.json"
    )

    # 1. 拉取远程插件列表（GitHub → Gitee 回退）
    remote: list[dict] | None = None
    for url in (github_raw, gitee_raw):
        try:
            async with httpx.AsyncClient(timeout=10) as cli:
                r = await cli.get(url)
                r.raise_for_status()
                remote = r.json()
                break
        except Exception:
            # 第一次失败继续尝试第二个地址；第二次失败再抛 502
            if url == gitee_raw:
                raise HTTPException(
                    status_code=502,
                    detail="无法获取远程插件列表（GitHub 与 Gitee 均失败）"
                )
            continue

    # 2. 本地已安装
    try:
        local_res = await list_extensions()
        installed_repos = {
            ext.repository.strip().rstrip("/").lower()
            for ext in local_res.extensions
            if ext.repository
        }
    except Exception:
        installed_repos = set()

    # 3. 合并状态
    def _with_status(p: dict):
        repo = p.get("repository", "").strip().rstrip("/").lower()
        parse = urlparse(p.get("repository", ""))
        path_parts = parse.path.strip("/").split("/")
        ext_id = f"{path_parts[0]}_{path_parts[1]}"
        return RemotePluginItem(
            id=ext_id,
            name=p.get("name", "未命名"),
            description=p.get("description", ""),
            author=p.get("author", "未知"),
            version=p.get("version", "1.0.0"),
            category=p.get("category", "Unknown"),
            repository=p.get("repository", ""),
            installed=repo in installed_repos,
        )

    return RemotePluginList(plugins=[_with_status(p) for p in remote])

# ------------------ 更新扩展（带备用仓库回退） ------------------
@router.put("/{ext_id}/update")
async def update_extension(ext_id: str):
    target = Path(EXT_DIR) / ext_id
    if not target.exists():
        raise HTTPException(status_code=404, detail="扩展未安装")

    # 1. 读取主/备仓库地址
    pkg_file = target / "package.json"
    repos: list[str] = []
    if pkg_file.exists():
        try:
            meta = json.loads(pkg_file.read_text(encoding="utf-8"))
            if meta.get("repository"):
                repos.append(meta["repository"].strip().rstrip("/"))
            if meta.get("backupRepository"):
                repos.append(meta["backupRepository"].strip().rstrip("/"))
        except Exception:
            pass

    # 2. 至少要有一个仓库
    if not repos:
        raise HTTPException(status_code=400, detail="缺少 repository / backupRepository 字段")

    # 3. 顺序 pull（主 → 备）
    last_err: Exception | None = None
    for idx, repo in enumerate(repos):
        try:
            # 第一次用本地已跟踪的远程；如果本地没有该 remote 则加进来
            remote_name = "origin" if idx == 0 else "backup"
            # 确保 remote 存在（静默添加，已存在会报错可忽略）
            subprocess.run(
                ["git", "-C", str(target), "remote", "add", remote_name, repo],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            # 真正拉取
            subprocess.run(
                ["git", "-C", str(target), "pull", remote_name, "--ff-only"],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            # 成功就结束
            return {"status": "updated", "remote": repo}
        except subprocess.CalledProcessError as e:
            last_err = e
            continue        # 失败就换备用地址

    # 4. 全部失败
    raise HTTPException(
        status_code=500,
        detail=f"主/备仓库均更新失败：{last_err and last_err.stderr}"
    )

from py.node_runner import node_mgr
from aiohttp import ClientSession
import aiohttp

http_sess: ClientSession | None = None

@router.on_event("startup")
async def startup():
    global http_sess
    http_sess = ClientSession()

@router.on_event("shutdown")
async def shutdown():
    await http_sess.close()
    for ext_id in list(node_mgr.exts.keys()):
        await node_mgr.stop(ext_id)

# 1. 启动扩展（幂等）
@router.post("/{ext_id}/start-node")
async def start_node(ext_id: str):
    """
    1. 没 index.js  -> 返回 mode='static'，前端收到后用旧路由
    2. 启动失败   -> 同上（回退）
    3. 启动成功   -> 返回 mode='node' + port
    """
    ext_dir = Path(EXT_DIR) / ext_id
    node_entry = ext_dir / "index.js"
    if not node_entry.exists():
        print(f"扩展 {ext_id} 没有入口文件，回退静态")
        return {"mode": "static"}          # ① 直接告诉前端用静态

    try:
        port = await node_mgr.start(ext_id)
        return {"mode": "node", "port": port}
    except Exception as e:
        print(f"Node 启动失败，回退静态：{str(e)}")
        return {"mode": "static"}          # ② 启动失败也回退

# 2. 停止扩展
@router.post("/{ext_id}/stop-node")
async def stop_node(ext_id: str):
    await node_mgr.stop(ext_id)
    return {"status": "stopped"}

# 3. 反向代理  /api/extensions/{ext_id}/node/*
@router.api_route("/{ext_id}/node/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy(ext_id: str, path: str, request: Request):
    if ext_id not in node_mgr.exts:
        raise HTTPException(404, "扩展未启动")
    port = node_mgr.exts[ext_id].port
    url = f"http://127.0.0.1:{port}/{path}"
    # 把原始请求方法、body、query、header 都透传
    body = await request.body()
    async with http_sess.request(
        method=request.method,
        url=url,
        params=request.query_params,
        headers={k: v for k, v in request.headers.items() if k.lower() != "host"},
        data=body
    ) as resp:
        content = await resp.read()
        return Response(content, status_code=resp.status, headers=dict(resp.headers))