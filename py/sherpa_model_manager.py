import asyncio, os, json, uuid, httpx, aiofiles
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from py.get_setting import DEFAULT_ASR_DIR

router = APIRouter(prefix="/sherpa-model")

MODEL_NAME = "sherpa-onnx-sense-voice-zh-en-ja-ko-yue"
MODELS = {
    "modelscope": {
        "url": "https://modelscope.cn/models/pengzhendong/sherpa-onnx-sense-voice-zh-en-ja-ko-yue/resolve/master/model.int8.onnx",
        "tokens_url": "https://modelscope.cn/models/pengzhendong/sherpa-onnx-sense-voice-zh-en-ja-ko-yue/resolve/master/tokens.txt",
    },
    "huggingface": {
        "url": "https://huggingface.co/csukuangfj/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2025-09-09/resolve/main/model.int8.onnx?download=true",
        "tokens_url": "https://huggingface.co/csukuangfj/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2025-09-09/resolve/main/tokens.txt?download=true",
    }
}

# ---------- 工具 ----------
def model_dir() -> Path:
    return Path(DEFAULT_ASR_DIR) / MODEL_NAME

def model_exists() -> bool:
    d = model_dir()
    return (d / "model.int8.onnx").is_file() and (d / "tokens.txt").is_file()

async def download_file(url: str, dest: Path, progress_id: str):
    tmp = dest.with_suffix(".downloading")
    async with httpx.AsyncClient(timeout=None, follow_redirects=True) as client:
        async with client.stream("GET", url) as resp:
            total = int(resp.headers.get("content-length", 0))
            done = 0
            async with aiofiles.open(tmp, "wb") as f:
                async for chunk in resp.aiter_bytes(1024 * 64):
                    await f.write(chunk)
                    done += len(chunk)
                    (Path(DEFAULT_ASR_DIR) / f"{progress_id}.json").write_text(
                        json.dumps({"done": done, "total": total})
                    )
    tmp.rename(dest)

# ---------- 接口 ----------
@router.get("/status")
def status():
    return {"exists": model_exists(), "model": MODEL_NAME}

@router.delete("/remove")
def remove():
    import shutil
    d = model_dir()
    if d.exists():
        shutil.rmtree(d)
    # 清理进度文件
    for f in Path(DEFAULT_ASR_DIR).glob("*.json"):
        f.unlink(missing_ok=True)
    return {"ok": True}

@router.get("/download/{source}")
async def download(source: str):
    if source not in MODELS:
        raise HTTPException(status_code=400, detail="bad source")
    if model_exists():
        raise HTTPException(status_code=400, detail="model already exists")

    progress_id = uuid.uuid4().hex
    model_subdir = model_dir()
    model_subdir.mkdir(parents=True, exist_ok=True)

    async def event_generator():
        # 启动两个下载任务
        asyncio.create_task(
            download_file(MODELS[source]["url"], model_subdir / "model.int8.onnx", progress_id)
        )
        asyncio.create_task(
            download_file(MODELS[source]["tokens_url"], model_subdir / "tokens.txt", progress_id + "_tok")
        )

        while True:
            await asyncio.sleep(0.5)
            try:
                data = json.loads((Path(DEFAULT_ASR_DIR) / f"{progress_id}.json").read_text())
                yield f"data: {json.dumps(data)}\n\n"
                if data["done"] == data["total"] and data["total"] > 0:
                    (Path(DEFAULT_ASR_DIR) / f"{progress_id}.json").unlink(missing_ok=True)
                    yield "data: close\n\n"
                    return
            except FileNotFoundError:
                yield f"data: {json.dumps({'done': 0, 'total': 0})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
