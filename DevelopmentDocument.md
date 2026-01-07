# 开发手册

## 项目概述

基于Super-Agent-Party开发

## 项目结构

```
super-agent-party-dev/
├── config/                      # 配置文件目录
│   ├── locales.json            # 国际化配置文件
│   └── settings_template.json  # 设置模板文件
├── py/                         # Python 模块目录
│   ├── a2a_tool.py            # A2A 工具实现
│   ├── agent_tool.py          # Agent 工具调用功能
│   ├── autoBehavior.py        # 自动行为系统
│   ├── blivedm/               # B站直播相关模块
│   ├── cli_tool.py            # 命令行工具
│   ├── code_interpreter.py    # 代码解释器
│   ├── comfyui_tool.py        # ComfyUI 工具
│   ├── custom_http.py         # 自定义HTTP请求
│   ├── dify_openai_async.py   # Dify OpenAI 异步客户端
│   ├── extensions.py          # 扩展系统
│   ├── get_setting.py         # 设置管理
│   ├── image_host.py          # 图片托管功能
│   ├── know_base.py           # 知识库功能
│   ├── llm_tool.py            # LLM 工具系统
│   ├── load_files.py          # 文件加载功能
│   ├── mcp_clients.py         # MCP 客户端
│   ├── node_runner.py         # 节点运行器
│   ├── pollinations.py        # Pollinations 工具
│   ├── qq_bot_manager.py      # QQ机器人管理器
│   ├── sherpa_asr.py          # 语音识别
│   ├── sherpa_model_manager.py # 模型管理器
│   ├── utility_tools.py       # 通用工具集
│   └── web_search.py          # 网络搜索功能
├── static/                     # 前端静态资源目录
│   ├── css/                   # CSS样式文件
│   ├── ext/                   # 扩展目录
│   ├── fontawesome/           # 图标库
│   ├── index.html             # 主页面
│   ├── js/                    # JavaScript 文件
│   │   ├── bundle.min.js      # 打包后的JS
│   │   ├── clipboard.min.js   # 剪贴板功能
│   │   ├── highlight.min.js   # 代码高亮
│   │   ├── locales.js         # 前端国际化
│   │   ├── markdown-it.min.js # Markdown解析
│   │   ├── mermaid.min.js     # Mermaid图表
│   │   ├── qrcode.min.js      # 二维码生成
│   │   ├── vue_data.js        # Vue数据模型
│   │   └── vue_methods.js     # Vue方法
│   ├── manifest.json          # Web应用清单
│   ├── source/                # 图片资源
│   └── vrm.html               # VRM模型页面
├── server.py                   # 主服务器文件
├── main.js                     # Electron主进程
├── requirements.txt            # Python依赖
├── package.json                # Node.js依赖
└── Dockerfile                  # Docker配置文件
```

## 核心功能模块

### 1. AI 模型集成

项目支持多种AI模型提供商，包括OpenAI、Dify等，通过统一的接口进行调用。

主要相关文件：
- `server.py`: 核心模型调用逻辑
- `py/dify_openai_async.py`: Dify OpenAI 异步客户端实现
- `py/llm_tool.py`: LLM工具系统

### 2. Agent 系统

Agent系统允许创建和配置多个具有不同功能的智能体，并支持它们之间的交互。

主要相关文件：
- `py/agent_tool.py`: Agent工具调用功能
- `config/settings_template.json`: Agent配置模板

### 3. 工具调用系统

项目实现了丰富的工具集，支持AI模型动态调用各种外部工具。

主要相关文件：
- `py/utility_tools.py`: 通用工具实现（时间、天气、维基百科、arXiv等）
- `py/llm_tool.py`: LLM工具系统

### 4. 自动行为系统

支持配置AI的自动行为，如定时触发、循环执行等。

主要相关文件：
- `py/autoBehavior.py`: 自动行为系统实现

### 5. 前端界面

基于Vue.js的前端界面，提供丰富的交互功能。

主要相关文件：
- `static/index.html`: 主页面
- `static/js/vue_data.js`: Vue数据模型
- `static/js/vue_methods.js`: Vue方法

## 配置系统

项目使用JSON格式的配置文件，主要配置包括：

- 模型设置（API密钥、基础URL、参数等）
- Agent配置
- 工具配置
- 系统设置（语言、主题等）

主要相关文件：
- `config/settings_template.json`: 设置模板
- `py/get_setting.py`: 设置管理

## 扩展系统

项目支持通过扩展机制添加新功能。

主要相关文件：
- `py/extensions.py`: 扩展系统实现
- `static/ext/`: 扩展目录

## 开发指南

### 注意事项
1. 实际使用过程中，对JavaScript模块的导入需要确保导入格式正确，部分系统没有预置的文件类型注册表， 
需要在server.py补充注册表如下
```python
import mimetypes

# === 强制注册所有 Web 和 3D 资源所需的 MIME 类型 ===
# 避免未注册导致导入时全部加载为text/plain模式
# JavaScript / 模块
mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("application/javascript", ".mjs")      # ES Modules
mimetypes.add_type("text/javascript", ".js")             # 兼容旧标准（可选）

# JSON 相关
mimetypes.add_type("application/json", ".json")

# 样式与字体
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("font/woff", ".woff")
mimetypes.add_type("font/woff2", ".woff2")
mimetypes.add_type("font/ttf", ".ttf")
mimetypes.add_type("font/otf", ".otf")

# 图片
mimetypes.add_type("image/png", ".png")
mimetypes.add_type("image/jpeg", ".jpg")
mimetypes.add_type("image/jpeg", ".jpeg")
mimetypes.add_type("image/gif", ".gif")
mimetypes.add_type("image/webp", ".webp")
mimetypes.add_type("image/svg+xml", ".svg")

# 音频 / 视频
mimetypes.add_type("audio/mpeg", ".mp3")
mimetypes.add_type("audio/ogg", ".ogg")
mimetypes.add_type("audio/wav", ".wav")
mimetypes.add_type("video/mp4", ".mp4")
mimetypes.add_type("video/webm", ".webm")

# 3D 模型 & VRM / glTF 生态（关键！）
mimetypes.add_type("model/gltf+json", ".gltf")
mimetypes.add_type("model/gltf-binary", ".glb")
mimetypes.add_type("application/octet-stream", ".vrm")     # VRM 通常用 binary
mimetypes.add_type("application/octet-stream", ".bin")     # glTF 外部 buffer
mimetypes.add_type("application/octet-stream", ".vrmc")    # 可能的变体
mimetypes.add_type("model/vnd.vrm+json", ".vrm")           # 实验性（部分工具使用）

# WebAssembly（Three.js 新版可能用到）
mimetypes.add_type("application/wasm", ".wasm")

# HTML / 文本
mimetypes.add_type("text/html", ".html")
mimetypes.add_type("text/html", ".htm")
mimetypes.add_type("text/plain", ".txt")

# 其他前端常用
mimetypes.add_type("application/xml", ".xml")
mimetypes.add_type("application/zip", ".zip")
mimetypes.add_type("application/x-icon", ".ico")

# Vue / 构建产物（如果你有 .vue 或构建输出）
mimetypes.add_type("text/javascript", ".umd.js")
mimetypes.add_type("application/json", ".map")  # source map

# 可选：允许加载本地文件时的通用二进制类型
mimetypes.add_type("application/octet-stream", ".dat")
mimetypes.add_type("application/octet-stream", ".data")
```

### 添加新功能的基本流程

1. **后端功能开发**:
   - 在`py/`目录下创建新的模块文件
   - 实现相应的功能和接口
   - 在`server.py`中注册路由或集成功能

2. **前端功能开发**:
   - 修改`static/index.html`添加界面元素
   - 在`static/js/vue_data.js`中添加数据模型
   - 在`static/js/vue_methods.js`中添加交互逻辑

3. **配置管理**:
   - 在`config/settings_template.json`中添加相应的配置项
   - 在`py/get_setting.py`中添加配置加载逻辑

### 工具开发

要添加新的工具，需要：

1. 实现工具函数（异步）
2. 定义工具的描述和参数（用于function calling）
3. 在适当的地方注册工具

示例：
```python
async def my_tool(param1, param2):
    # 实现工具逻辑
    return result

my_tool_def = {
    "type": "function",
    "function": {
        "name": "my_tool",
        "description": "工具描述",
        "parameters": {
            # 参数定义
        }
    }
}
```

### Agent 开发

要创建新的Agent，需要：

1. 定义Agent的系统提示词
2. 在配置中启用Agent
3. 使用agent_tool调用Agent

### 即插即用开发
1. 将自己的智能体系统封装成openai-api模式的接口
2. 将输入送入接口后，在系统内部进行多智能体或多步的处理，该项目主体来看对多智能体协同支持较弱
3. 将输出内容以文本形式返回，在前端对输入内容进行解析


## 部署方式

项目支持多种部署方式：

1. **本地开发**:
   - 运行`python server.py`启动后端服务
   - 访问`http://localhost:3456`

2. **Electron 桌面应用**:
   - 运行`npm run dev`进行开发
   - 运行`npm run build`构建应用

3. **Docker 部署**:
   - 使用提供的Dockerfile构建镜像
   - 运行容器


