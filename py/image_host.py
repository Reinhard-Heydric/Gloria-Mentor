import base64
import logging
import os
import random
import re
import tempfile
import time

import requests
from py.get_setting import UPLOAD_FILES_DIR, load_settings


async def upload_image_host(url):
    settings = await load_settings()
    # 检查图床功能是否开启
    if not settings["BotConfig"]["imgHost_enabled"]:
        return url
    
    # 处理本地文件上传
    if 'uploaded_files' in url:
        file_name = url.split("/")[-1]
        file_path = os.path.join(UPLOAD_FILES_DIR, file_name)
        return await _upload_file(settings, file_path)
    
    # 处理外部URL上传
    try:
        # 下载图片到临时文件
        response = requests.get(url, stream=True, timeout=10)
        if response.status_code != 200:
            logging.error(f"下载图片失败: HTTP {response.status_code} - {url}")
            return url
        
        # 获取内容类型和扩展名
        content_type = response.headers.get('Content-Type', '')
        ext_map = {
            'image/jpeg': '.jpg',
            'image/png': '.png',
            'image/gif': '.gif',
            'image/webp': '.webp',
            'image/svg+xml': '.svg',
        }
        ext = ext_map.get(content_type.split(';')[0], '.bin')
        
        # 创建临时文件
        with tempfile.NamedTemporaryFile(
            suffix=ext, 
            dir=UPLOAD_FILES_DIR,
            delete=False
        ) as tmp_file:
            for chunk in response.iter_content(chunk_size=8192):
                tmp_file.write(chunk)
            file_path = tmp_file.name
        
        logging.info(f"下载外部图片到临时文件: {file_path}")
        return await _upload_file(settings, file_path)
    
    except Exception as e:
        logging.error(f"处理外部图片异常: {str(e)}")
        return url

async def _upload_file(settings, file_path):
    """实际执行文件上传的内部函数"""
    # 确保文件存在
    if not os.path.exists(file_path):
        logging.error(f"文件不存在: {file_path}")
        return f"文件不存在: {file_path}"
    
    file_name = os.path.basename(file_path)
    is_temp_file = 'tmp' in file_path  # 标记临时文件
    
    try:
        # SM.MS图床处理
        if settings["BotConfig"]["imgHost"] == "smms":
            api_key = settings["BotConfig"].get("SMMS_api_key")
            if not api_key:
                logging.warning("SM.MS API key未配置，跳过上传")
                return "SM.MS API key未配置，跳过上传"
            
            headers = {"Authorization": api_key}
            upload_url = "https://sm.ms/api/v2/upload"
            
            with open(file_path, "rb") as f:
                files = {"smfile": (file_name, f)}
                response = requests.post(upload_url, headers=headers, files=files)
            
            result = response.json()
            
            # 成功上传
            if response.status_code == 200 and result.get("success"):
                return result["data"]["url"]
            
            # 处理重复图片情况
            elif result.get("code") == "image_repeated":
                logging.info("检测到重复图片（已存在SM.MS服务器）")
                
                # 尝试从错误消息中提取URL
                message = result.get("message", "")
                url_match = re.search(r'https?://[^\s]+', message)
                
                if url_match:
                    existing_url = url_match.group(0)
                    logging.info(f"使用已有图片URL: {existing_url}")
                    return existing_url
                
                # 如果正则提取失败，尝试从images字段获取
                elif result.get("images"):
                    existing_url = result["images"]
                    logging.info(f"使用已有图片URL: {existing_url}")
                    return existing_url
                
                # 如果都没有找到URL，返回原始文件路径
                else:
                    logging.warning("无法从重复图片响应中提取URL")
                    return "无法从重复图片响应中提取URL"
            
            # 处理其他错误
            else:
                error_msg = result.get("message", "未知错误")
                error_code = result.get("code", "未知代码")
                logging.error(f"SM.MS上传失败: {error_msg} (代码: {error_code})")
                return f"SM.MS上传失败: {error_msg} (代码: {error_code})"
        
        # EasyImage图床处理
        elif settings["BotConfig"]["imgHost"] == "easyImage2":
            EI2_url = settings["BotConfig"]["EI2_base_url"]
            EI2_token = settings["BotConfig"]["EI2_api_key"]
            
            with open(file_path, "rb") as f:
                files = {"image": (file_name, f)}
                data = {"token": EI2_token}
                response = requests.post(EI2_url, data=data, files=files)
            
            if response.status_code == 200:
                return response.json().get("url")
            else:
                logging.error(f"EasyImage上传失败: {response.status_code}")
                return f"EasyImage上传失败: {response.status_code}"

        # Gitee图床处理 - 新增部分
        elif settings["BotConfig"]["imgHost"] == "gitee":
            # 获取Gitee配置
            repo_owner = settings["BotConfig"].get("gitee_repo_owner")
            repo_name = settings["BotConfig"].get("gitee_repo_name")
            branch = settings["BotConfig"].get("gitee_branch", "master")  # 默认master分支
            access_token = settings["BotConfig"].get("gitee_token")
            
            # 检查配置是否完整
            if not all([repo_owner, repo_name, branch, access_token]):
                missing = [k for k, v in {
                    "gitee_repo_owner": repo_owner,
                    "gitee_repo_name": repo_name,
                    "gitee_branch": branch,
                    "gitee_access_token": access_token
                }.items() if not v]
                logging.error(f"Gitee配置不完整，缺少: {', '.join(missing)}")
                return f"Gitee配置不完整，缺少: {', '.join(missing)}"
            # 新增：生成唯一文件名
            base, ext = os.path.splitext(file_name)
            # 替换特殊字符为下划线
            base = re.sub(r'[^\w\-]', '_', base)
            # 添加时间戳和随机数确保唯一
            unique_name = f"{base}_{int(time.time()*1000)}_{random.randint(1000,9999)}{ext}"
            file_name = unique_name
            # 检查文件大小（Gitee限制1MB）
            file_size = os.path.getsize(file_path)
            if file_size > 1024 * 1024:  # 1MB
                logging.warning(f"文件大小超过1MB（{file_size}字节），Gitee不支持，跳过上传")
                return f"文件大小超过1MB（{file_size}字节），Gitee不支持，跳过上传"
            
            # 读取文件并编码为Base64
            try:
                with open(file_path, "rb") as f:
                    image_data = base64.b64encode(f.read()).decode("utf-8")
            except Exception as e:
                logging.error(f"读取文件失败: {str(e)}")
                return f"读取文件失败: {str(e)}"
            
            # 构造API请求
            api_url = f"https://gitee.com/api/v5/repos/{repo_owner}/{repo_name}/contents/{file_name}"
            headers = {"Content-Type": "application/json;charset=UTF-8"}
            payload = {
                "access_token": access_token,
                "content": image_data,
                "message": f"Upload image {file_name}",
                "branch": branch
            }
            
            try:
                response = requests.post(api_url, json=payload, headers=headers, timeout=15)
                response_data = response.json()
                
                # 成功上传
                if response.status_code == 201:
                    # 构造公网可访问的raw链接
                    raw_url = f"https://gitee.com/{repo_owner}/{repo_name}/raw/{branch}/{file_name}"
                    logging.info(f"Gitee上传成功！URL: {raw_url}")
                    return raw_url
                
                # 处理文件已存在的情况
                elif response.status_code == 409:
                    existing_url = f"https://gitee.com/{repo_owner}/{repo_name}/raw/{branch}/{file_name}"
                    logging.info(f"文件已存在于Gitee仓库，使用现有URL: {existing_url}")
                    return existing_url
                
                # 处理其他错误
                else:
                    error_msg = response_data.get("message", "未知错误")
                    logging.error(f"Gitee上传失败: {error_msg} (状态码: {response.status_code})")
                    return f"Gitee上传失败: {error_msg} (状态码: {response.status_code})"
                    
            except Exception as e:
                logging.error(f"Gitee上传请求异常: {str(e)}")
                return f"Gitee上传请求异常: {str(e)}"

        # GitHub图床处理 - 新增部分
        elif settings["BotConfig"]["imgHost"] == "github":
            # 获取GitHub配置
            repo_owner = settings["BotConfig"].get("github_repo_owner")
            repo_name = settings["BotConfig"].get("github_repo_name")
            branch = settings["BotConfig"].get("github_branch", "main")  # 默认main分支
            access_token = settings["BotConfig"].get("github_token")
            
            # 检查配置是否完整
            if not all([repo_owner, repo_name, branch, access_token]):
                missing = [k for k, v in {
                    "github_repo_owner": repo_owner,
                    "github_repo_name": repo_name,
                    "github_branch": branch,
                    "github_token": access_token
                }.items() if not v]
                logging.error(f"GitHub配置不完整，缺少: {', '.join(missing)}")
                return f"GitHub配置不完整，缺少: {', '.join(missing)}"
            # 新增：生成唯一文件名
            base, ext = os.path.splitext(file_name)
            # 替换特殊字符为下划线
            base = re.sub(r'[^\w\-]', '_', base)
            # 添加时间戳和随机数确保唯一
            unique_name = f"{base}_{int(time.time()*1000)}_{random.randint(1000,9999)}{ext}"
            file_name = unique_name
            # 检查文件大小（GitHub限制100MB，但图床建议小于10MB）
            file_size = os.path.getsize(file_path)
            if file_size > 10 * 1024 * 1024:  # 10MB
                logging.warning(f"文件大小超过10MB（{file_size}字节），建议压缩后上传")
                # 不直接返回，继续尝试上传
            
            # 读取文件并编码为Base64
            try:
                with open(file_path, "rb") as f:
                    image_data = base64.b64encode(f.read()).decode("utf-8")
            except Exception as e:
                logging.error(f"读取文件失败: {str(e)}")
                return f"读取文件失败: {str(e)}"
            
            # 构造API请求
            api_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/contents/{file_name}"
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github.v3+json"
            }
            payload = {
                "message": f"Upload image {file_name}",
                "content": image_data,
                "branch": branch
            }
            
            try:
                response = requests.put(api_url, json=payload, headers=headers, timeout=15)
                response_data = response.json()
                
                # 成功上传 (201 Created)
                if response.status_code == 201:
                    # 构造CDN加速链接
                    cdn_url = f"https://cdn.jsdelivr.net/gh/{repo_owner}/{repo_name}@{branch}/{file_name}"
                    logging.info(f"GitHub上传成功！CDN URL: {cdn_url}")
                    return cdn_url
                
                # 处理文件已存在的情况 (422 Unprocessable Entity)
                elif response.status_code == 422:
                    # 检查错误信息确认是否为文件已存在
                    if any("already exists" in msg.lower() for msg in response_data.get("errors", [])):
                        # 构造CDN加速链接
                        cdn_url = f"https://cdn.jsdelivr.net/gh/{repo_owner}/{repo_name}@{branch}/{file_name}"
                        logging.info(f"文件已存在于GitHub仓库，使用CDN URL: {cdn_url}")
                        return cdn_url
                    else:
                        error_msg = response_data.get("message", "未知错误")
                        logging.error(f"GitHub上传失败: {error_msg} (状态码: {response.status_code})")
                        return f"GitHub上传失败: {error_msg} (状态码: {response.status_code})"
                
                # 处理其他错误
                else:
                    error_msg = response_data.get("message", "未知错误")
                    logging.error(f"GitHub上传失败: {error_msg} (状态码: {response.status_code})")
                    return f"GitHub上传失败: {error_msg} (状态码: {response.status_code})"
                    
            except Exception as e:
                logging.error(f"GitHub上传请求异常: {str(e)}")
                return f"GitHub上传请求异常: {str(e)}"

        # 未知图床类型
        else:
            logging.warning(f"未知图床类型: {settings['BotConfig']['imgHost']}")
            return f"未知图床类型: {settings['BotConfig']['imgHost']}"
    
    except Exception as e:
        logging.error(f"图床上传异常: {str(e)}")
        return f"图床上传异常: {str(e)}"
    
    finally:
        # 清理临时文件
        if is_temp_file and os.path.exists(file_path):
            try:
                os.remove(file_path)
                logging.info(f"已清理临时文件: {file_path}")
            except Exception as e:
                logging.error(f"清理临时文件失败: {str(e)}")