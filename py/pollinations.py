import base64

import requests
from py.get_setting import load_settings,get_host,get_port,UPLOAD_FILES_DIR
from openai import AsyncClient
import uuid
async def pollinations_image(prompt: str, width=512, height=512, model="flux"):
    settings = await load_settings()
    
    # Check if the provided values are default ones, if so, override them with settings
    if width == 512:
        width = settings["text2imgSettings"]["pollinations_width"]
    if height == 512:
        height = settings["text2imgSettings"]["pollinations_height"]
    if model == "flux":
        model = settings["text2imgSettings"]["pollinations_model"]
    
    # Convert prompt into a URL-compatible format
    prompt = prompt.replace(" ", "%20")
    url = f"https://image.pollinations.ai/prompt/{prompt}?width={width}&height={height}&model={model}&nologo=true&enhance=true&private=true&safe=true"
    res_data = requests.get(url).content
    image_id = str(uuid.uuid4())
    # 将图片保存到本地UPLOAD_FILES_DIR，文件名为image_id，返回本地文件路径
    with open(f"{UPLOAD_FILES_DIR}/{image_id}.png", "wb") as f:
        f.write(res_data)
    return f"![image]({url})"

pollinations_image_tool = {
    "type": "function",
    "function": {
        "name": "pollinations_image",
        "description": "通过英文prompt生成图片，并返回markdown格式的图片链接，你必须直接以原markdown格式发给用户，用户才能直接看到图片。\n当你需要发送图片时，请将图片的URL放在markdown的图片标签中，例如：\n\n![图片名](图片URL)\n\n，图片markdown必须另起并且独占一行！",
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "需要生成图片的英文prompt，例如：A little girl in a red hat。你可以尽可能的丰富你的prompt，以获得更好的效果",
                },
                "width": {
                    "type": "number",
                    "description": "图片宽度",
                    "default":512
                },
                "height": {
                    "type": "number",
                    "description": "图片高度",
                    "default": 512
                },
                "model": {
                    "type": "string",
                    "description": "使用的模型",
                    "default": "flux",
                    "enum": ["flux", "turbo"],
                }
            },
            "required": ["prompt"],
        },
    },
}

async def openai_image(prompt: str, size="auto"):
    settings = await load_settings()

    # Check if the provided values are default ones, if so, override them with settings
    if size == "auto":
        size = settings["text2imgSettings"]["size"]

    model = settings["text2imgSettings"]["model"]

    base_url = settings["text2imgSettings"]["base_url"]
    api_key = settings["text2imgSettings"]["api_key"]
    try:
        client = AsyncClient(api_key=api_key,base_url=base_url)
    
        response = await client.images.generate(prompt=prompt, size=size, model=model)
    except Exception as e:
        print(e)
        return f"ERROR: {e}"
    
    res_url = response.data[0].url
    res = f"![image]({res_url})"
    print(res)
    if res_url is None:
        res = response.data[0].b64_json
        HOST = get_host()
        if HOST == '0.0.0.0':
            HOST = '127.0.0.1'
        PORT = get_port()
        image_id = str(uuid.uuid4())
        # 将图片保存到本地UPLOAD_FILES_DIR，文件名为image_id，返回本地文件路径
        with open(f"{UPLOAD_FILES_DIR}/{image_id}.png", "wb") as f:
            f.write(base64.b64decode(res))
        res = f"![image](http://{HOST}:{PORT}/uploaded_files/{image_id}.png)"
    else:
        res_data = requests.get(res_url).content
        image_id = str(uuid.uuid4())
        # 将图片保存到本地UPLOAD_FILES_DIR，文件名为image_id，返回本地文件路径
        with open(f"{UPLOAD_FILES_DIR}/{image_id}.png", "wb") as f:
            f.write(res_data)
    return res
        
openai_image_tool = {
    "type": "function",
    "function": {
        "name": "openai_image",
        "description": "通过英文prompt生成图片，并返回markdown格式的图片链接，你必须直接以原markdown格式发给用户，用户才能直接看到图片。\n当你需要发送图片时，请将图片的URL放在markdown的图片标签中，例如：\n\n![图片名](图片URL)\n\n，图片markdown必须另起并且独占一行！",
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "需要生成图片的英文prompt，例如：A little girl in a red hat。你可以尽可能的丰富你的prompt，以获得更好的效果",
                },
                "size": {
                    "type": "string",
                    "description": "图片大小，默认为auto，即自动选择最优大小",
                    "default": "auto",
                    "enum": ["auto", "1024x1024", "1536x1024", "1024x1536", "256x256", "512x512", "1792x1024", "1024x1792"],
                }
            },
            "required": ["prompt"],
        },
    },
}

async def siliconflow_image(prompt: str, size="1024x1024"):
    settings = await load_settings()

    # Check if the provided values are default ones, if so, override them with settings
    if size == "1024x1024":
        size = settings["text2imgSettings"]["size"]

    model = settings["text2imgSettings"]["model"]

    base_url = settings["text2imgSettings"]["base_url"]
    api_key = settings["text2imgSettings"]["api_key"]
    try:
        client = AsyncClient(api_key=api_key,base_url=base_url)
    
        response = await client.images.generate(prompt=prompt, size=size, model=model)
    except Exception as e:
        print(e)
        return f"ERROR: {e}"
    
    try:
        res_url = response.data[0].url
        res_data = requests.get(res_url).content
        image_id = str(uuid.uuid4())
        # 将图片保存到本地UPLOAD_FILES_DIR，文件名为image_id，返回本地文件路径
        with open(f"{UPLOAD_FILES_DIR}/{image_id}.png", "wb") as f:
            f.write(res_data)
        res = f"![image]({response.data[0].url})"
    except Exception as e:
        print(e)
        return f"ERROR: {e}"
    return res

siliconflow_image_tool = {
    "type": "function",
    "function": {
        "name": "siliconflow_image",
        "description": "通过英文prompt生成图片，并返回markdown格式的图片链接，你必须直接以原markdown格式发给用户，用户才能直接看到图片。\n当你需要发送图片时，请将图片的URL放在markdown的图片标签中，例如：\n\n![图片名](图片URL)\n\n，图片markdown必须另起并且独占一行！",
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "需要生成图片的英文prompt，例如：A little girl in a red hat。你可以尽可能的丰富你的prompt，以获得更好的效果",
                },
                "size": {
                    "type": "string",
                    "description": "图片大小",
                    "default": "1024x1024", 
                    "enum": ["1024x1024", "960x1280", "768x1024", "720x1440", "720x1280"],
                }
            },
            "required": ["prompt"],
        },
    }
}