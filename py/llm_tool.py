import base64
import json

import aiohttp
from py.get_setting import load_settings
from openai import AsyncOpenAI
from ollama import AsyncClient as OllamaClient


async def get_llm_tool(settings):
    llm_list = []

    llmTools = settings['llmTools']

    for llmTool in llmTools:
        if llmTool['enabled']:
            llm_list.append({"name": llmTool['name'], "description": llmTool['description']})
    if len(llm_list) > 0:
        llm_list = json.dumps(llm_list, ensure_ascii=False, indent=4)
        llm_tool = {
            "type": "function",
            "function": {
                "name": "custom_llm_tool",
                "description": f"custom_llm_tool工具可以调用工具列表中的通用工具。请不要混淆custom_llm_tool和tool_name字段要填入的工具名称。以下是工具列表：\n{llm_list}\n\n如果LLM工具返回的内容包含图片，则返回的图片URL或本地路径，请直接写成：![image](图片URL)格式发给用户，用户就能看到图片了",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "tool_name": {
                            "type": "string",
                            "description": "需要调用的工具名称",
                        },
                        "query": {
                            "type": "string",
                            "description": "需要向工具发送的问题",
                        },
                        "image_url": {
                            "type": "string",
                            "description": "需要向工具发送的图片URL，可选，来自本地服务器上的图片URL也可以填入（例如：http://127.0.0.1:3456/xxx.jpg），会被自动处理为base64编码发送",
                        }
                    },
                    "required": ["tool_name","query"]
                }
            }
        }
        return llm_tool
    else:
        return None
    
async def get_image_base64(image_url: str) -> str:
    """下载图片并转换为base64编码"""
    async with aiohttp.ClientSession() as session:
        async with session.get(image_url,headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'}) as response:
            if response.status != 200:
                raise ValueError(f"Failed to download image from {image_url}")
            image_data = await response.read()
            return base64.b64encode(image_data).decode('utf-8')
        
async def get_image_media_type(image_url: str) -> str:
    # 根据image_url类型调整
    if image_url.endswith('.png'):
        media_type = 'image/png'
    elif image_url.endswith('.jpg') or image_url.endswith('.jpeg'):
        media_type = 'image/jpeg'
    elif image_url.endswith('.webp'):
        media_type = 'image/webp'
    elif image_url.endswith('.gif'):
        media_type = 'image/gif'
    elif image_url.endswith('.bmp'):
        media_type = 'image/bmp'
    elif image_url.endswith('.tiff'):
        media_type = 'image/tiff'
    elif image_url.endswith('.ico'):
        media_type = 'image/x-icon'
    elif image_url.endswith('.svg'):
        media_type = 'image/svg+xml'
    else:
        media_type = 'image/png'
    return media_type

async def custom_llm_tool(tool_name, query, image_url=None):
    print(f"调用LLM工具：{tool_name}")
    settings = await load_settings()
    llmTools = settings['llmTools']
    for llmTool in llmTools:
        if llmTool['enabled'] and llmTool['name'] == tool_name:
            if llmTool['type'] == 'ollama':
                client = OllamaClient(host=llmTool['base_url'])
                try:
                    content = query
                    
                    # 处理图片输入
                    if image_url:
                        base64_image = await get_image_base64(image_url)
                        media_type = await get_image_media_type(image_url)
                        content = [
                            {"type": "text", "text": query},
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": base64_image
                                }
                            }
                        ]

                    # 调用Ollama API
                    response = await client.chat(
                        model=llmTool['model'],
                        messages=[{"role": "user", "content": content}],
                    )
                    return response.message.content
                except Exception as e:
                    return str(e)
            else:
                client = AsyncOpenAI(api_key=llmTool['api_key'],base_url=llmTool['base_url'])
                try:
                    if image_url:
                        base64_image = await get_image_base64(image_url)
                        # 根据image_url类型调整
                        media_type = await get_image_media_type(image_url)
                        prompt = [
                            {
                                "type": "image",
                                "image_url": {"url": f"data:{media_type};base64,{base64_image}"},
                            },
                            {
                                "type": "text",
                                "text": query
                            }
                        ]
                        response = await client.chat.completions.create(
                            model=llmTool['model'],
                            messages=[
                                {"role": "user", "content": prompt},
                            ],
                        )
                    else:
                        response = await client.chat.completions.create(
                            model=llmTool['model'],
                            messages=[
                                {"role": "user", "content": query},
                            ],
                        )
                    return response.choices[0].message.content
                except Exception as e:
                    return str(e)