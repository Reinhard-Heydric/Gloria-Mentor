# sherpa_asord.py
from pathlib import Path
import sherpa_onnx
import soundfile as sf
from io import BytesIO
from py.get_setting import DEFAULT_ASR_DIR

import platform

def _nvidia_gpu_count() -> int:
    """返回可用 NVIDIA GPU 数量；驱动或库缺失时返回 0"""
    try:
        import pynvml          # nvidia-ml-py 的顶层包名
        pynvml.nvmlInit()
        return pynvml.nvmlDeviceGetCount()
    except Exception:          # 驱动没装、权限不足、库缺失等都算“没有 GPU”
        return 0

def _best_provider() -> str:
    """返回 cpu / cuda / coreml 三者之一"""
    if _nvidia_gpu_count() > 0:
        return 'cuda'
    if platform.system() == 'Darwin' and platform.machine() == 'arm64':
        return 'coreml'
    return 'cpu'


# 默认模型子目录名
DEFAULT_MODEL_NAME = "sherpa-onnx-sense-voice-zh-en-ja-ko-yue"
DEVICE = _best_provider()
print(f"使用 {DEVICE} 设备")

async def sherpa_recognize(audio_bytes: bytes, model_name: str = None):
    """
    用 Sherpa 识别音频
    参数:
        audio_bytes: 音频字节
        model_name:  子目录名，None 则使用默认模型
    返回:
        识别文本
    """
    model_name = model_name or DEFAULT_MODEL_NAME
    model_dir = Path(DEFAULT_ASR_DIR) / model_name
    model = model_dir / "model.int8.onnx"
    tokens = model_dir / "tokens.txt"

    if not model.is_file() or not tokens.is_file():
        raise ValueError(f"Sherpa 模型文件未找到，目录={model_dir}")

    recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
        model=str(model),
        tokens=str(tokens),
        num_threads=4,
        provider=DEVICE,
        use_itn=True,
        debug=False,
    )

    try:
        with BytesIO(audio_bytes) as audio_file:
            audio, sample_rate = sf.read(audio_file, dtype="float32", always_2d=True)
            audio = audio[:, 0]
            stream = recognizer.create_stream()
            stream.accept_waveform(sample_rate, audio)
            recognizer.decode_stream(stream)
            return stream.result.text
    except Exception as e:
        raise RuntimeError(f"Sherpa ASR 处理失败: {e}")
