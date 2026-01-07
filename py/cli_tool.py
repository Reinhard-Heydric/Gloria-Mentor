#!/usr/bin/env python3
import asyncio
import os
import subprocess
import sys
from pathlib import Path

def get_shell_environment():
    """通过子进程获取完整的 shell 环境"""
    shell = os.environ.get('SHELL', '/bin/zsh')
    home = Path.home()
    
    # 尝试不同的配置文件
    config_commands = [
        f'source {home}/.zshrc && env',
        f'source {home}/.bash_profile && env', 
        f'source {home}/.bashrc && env',
        'env'  # 最后回退到当前环境
    ]
    
    for cmd in config_commands:
        try:
            result = subprocess.run(
                [shell, '-i', '-c', cmd],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                # 解析环境变量输出
                for line in result.stdout.splitlines():
                    if '=' in line:
                        var_name, var_value = line.split('=', 1)
                        os.environ[var_name] = var_value
                print("Successfully loaded environment from shell")
                return
        except Exception as e:
            print(f"Failed to load environment with command '{cmd}': {e}")
            continue
    
    print("Warning: Could not load shell environment, using current environment")

# 在导入 Claude SDK 之前设置环境变量
get_shell_environment()

# 现在导入 Claude SDK
import anyio
from claude_agent_sdk import query, ClaudeAgentOptions, AssistantMessage,ResultMessage, TextBlock
from py.get_setting import load_settings

from typing import AsyncIterator, Union

async def claude_code_async(prompt) -> str | AsyncIterator[str]:
    """返回 str（报错）或 AsyncIterator[str]（正常流式输出）。"""

    # 2. 工作目录检查
    settings = await load_settings()
    CLISettings = settings.get("CLISettings", {})
    cwd = CLISettings.get("cc_path")
    ccSettings = settings.get("ccSettings", {})
    if not cwd or not cwd.strip():
        return "No working directory is set, please set the working directory first!"
    extra_config = {}
    if ccSettings.get("enabled"):
        extra_config = {
            "ANTHROPIC_BASE_URL": ccSettings.get("base_url"),
            "ANTHROPIC_API_KEY": ccSettings.get("api_key"),
            "ANTHROPIC_MODEL": ccSettings.get("model"),
        }
        # 确保所有环境变量的值为字符串
        extra_config = {
            k: str(v) if v is not None else ""
            for k, v in extra_config.items()
        }
        print(f"Using Claude Code with the following settings: {extra_config}")
    # 3. 正常场景：返回异步生成器
    async def _stream() -> AsyncIterator[str]:
        options = ClaudeAgentOptions(
            cwd=cwd,
            permission_mode='acceptEdits',
            continue_conversation=True,
            env={
                **os.environ,
                **extra_config
            }
        )
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        yield block.text

    return _stream()

cli_info = """这是一个交互式命令行工具，专门帮助用户完成软件工程任务。

  可以协助您：
  - 编写、调试和重构代码
  - 搜索和分析文件内容
  - 运行构建和测试
  - 管理 Git 操作
  - 代码审查和优化
  - 以及其他编程相关的任务

  运行在您的本地环境中，可以访问文件系统并使用各种工具来帮助您完成工作。
"""

claude_code_tool = {
    "type": "function",
    "function": {
        "name": "claude_code_async",
        "description": f"你可以和控制CLI的智能体Claude Code进行交互。{cli_info}",
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "你想让Claude Code执行的指令，最好用自然语言交流，例如：请帮我创建一个文件，文件名为test.txt，文件内容为hello world",
                }
            },
            "required": ["prompt"],
        },
    },
}

async def qwen_code_async(prompt: str) -> str | AsyncIterator[str]:
    """
    返回：
      str                    – 出错信息（如未设置工作目录）
      AsyncIterator[str]     – 正常流式输出/错误流
    """
    # 1. 参数校验（工作目录）
    settings = await load_settings()
    CLISettings = settings.get("CLISettings", {})
    cwd = CLISettings.get("cc_path")
    qcSettings = settings.get("qcSettings", {})

    if not cwd or not cwd.strip():
        return "No working directory is set, please set the working directory first!"

    # 2. 构造环境变量
    extra_config: dict[str, str] = {}
    if qcSettings.get("enabled"):
        extra_config = {
            "OPENAI_BASE_URL": str(qcSettings.get("base_url") or ""),
            "OPENAI_API_KEY":  str(qcSettings.get("api_key")  or ""),
            "OPENAI_MODEL":    str(qcSettings.get("model")    or ""),
        }

    # 3. 内层异步生成器：真正干活
    async def _stream() -> AsyncIterator[str]:
        process = await asyncio.create_subprocess_shell(
            f'qwen -p "{prompt}"',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env={**os.environ, **extra_config},
        )

        async def read_stream(stream, *, is_error: bool = False):
            async for line in stream:
                prefix = "[ERROR] " if is_error else ""
                yield f"{prefix}{line.decode('utf-8').rstrip()}"

        async for out in _merge_streams(
            read_stream(process.stdout),
            read_stream(process.stderr, is_error=True),
        ):
            yield out

        await process.wait()

    # 4. 返回生成器
    return _stream()

async def _merge_streams(*streams):
    """合并多个异步流"""
    streams = [s.__aiter__() for s in streams]
    while streams:
        for stream in list(streams):
            try:
                item = await stream.__anext__()
                yield item
            except StopAsyncIteration:
                streams.remove(stream)


qwen_code_tool = {
    "type": "function",
    "function": {
        "name": "qwen_code_async",
        "description": f"你可以和控制CLI的智能体Qwen Code进行交互。{cli_info}",
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "你想让Qwen Code执行的指令，最好用自然语言交流，例如：请帮我创建一个文件，文件名为test.txt，文件内容为hello world",
                }
            },
            "required": ["prompt"],
        },
    },
}