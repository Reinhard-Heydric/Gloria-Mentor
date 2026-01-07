import asyncio
import httpx
from tiktoken_ext import openai_public
import tiktoken_ext
from langchain_core.embeddings import Embeddings
import requests
import os
if __name__ == "__main__":
    from load_files import get_files_json
    from get_setting import load_settings,base_path
else:
    from py.load_files import get_files_json
    from py.get_setting import load_settings,base_path
def get_tiktoken_cache_path():
    cache_path = os.path.join(base_path, "tiktoken_cache")
    os.makedirs(cache_path, exist_ok=True)
    return cache_path

# 在程序启动时设置环境变量
os.environ["TIKTOKEN_CACHE_DIR"] = get_tiktoken_cache_path()

import json
from pathlib import Path
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain.retrievers import EnsembleRetriever
from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document
from langchain_community.vectorstores import FAISS
from typing import List, Dict

from langchain_core.documents import Document
from py.get_setting import KB_DIR

class MyOpenAICompatibleEmbeddings(Embeddings):
    def __init__(self, base_url: str, model: str, api_key: str = "empty"):
        self.base_url = base_url
        self.model = model
        self.api_key = api_key

    def embed_query(self, text: str) -> List[float]:
        response = requests.post(
            f"{self.base_url}/embeddings",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"model": self.model, "input": text}
        )
        return response.json()["data"][0]["embedding"]

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        response = requests.post(
            f"{self.base_url}/embeddings",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"model": self.model, "input": texts}
        )
        return [r["embedding"] for r in response.json()["data"]]

def chunk_documents(results: List[Dict], cur_kb) -> List[Dict]:
    """为每个文件单独分块并添加元数据"""
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=cur_kb["chunk_size"],
        chunk_overlap=cur_kb["chunk_overlap"],
        separators=["\n\n", "\n", "。", "！", "？", "!", "?", "."]
    )
    
    all_docs = []
    for doc in results:
        chunks = text_splitter.split_text(doc["content"])
        for chunk in chunks:
            all_docs.append(Document(
                page_content=chunk,
                metadata={
                    "file_path": doc["file_path"],
                    "file_name": doc["file_name"],
                    "doc_id": f"{doc['file_path']}_{len(all_docs)}"  # 唯一标识
                }
            ))
    return all_docs

def build_vector_store(docs: List[Document], kb_id, cur_kb: Dict, cur_vendor: str):
    """构建并保存双索引（参数修正版）"""
    # 参数校验
    if not isinstance(docs, list) or not all(isinstance(d, Document) for d in docs):
        raise ValueError("Input must be a list of Document objects")
    
    # ========== BM25索引构建 ==========
    try:
        kb_dir = Path(KB_DIR)  # 根目录
        if not kb_dir.exists():
            kb_dir.mkdir(parents=True, exist_ok=True)
        
        save_dir = kb_dir / str(kb_id)  # 知识库专属目录
        save_dir.mkdir(parents=True, exist_ok=True)  # 确保目录存在

        bm25_path = save_dir / "bm25_index.json"
        
        # 写入前做空值检查
        if not docs:
            raise ValueError("Documents list is empty")
        # 保存文档数据
        with open(bm25_path, "w", encoding="utf-8") as f:
            json.dump({
                "docs": [
                    {
                        "page_content": doc.page_content,
                        "metadata": doc.metadata
                    } for doc in docs
                ]
            }, f, ensure_ascii=False)
    except Exception as e:
        raise RuntimeError(f"Failed to save BM25 index: {str(e)}")
    # ========== 向量索引构建 ==========
    try:
        embeddings = MyOpenAICompatibleEmbeddings(
            model=cur_kb["model"],
            api_key=cur_kb["api_key"],
            base_url=cur_kb["base_url"],
        )
        # 批量处理文档
        batch_size = 5  # 根据显存调整
        vector_db = None
        
        for i in range(0, len(docs), batch_size):
            batch = docs[i:i+batch_size]
            
            if vector_db is None:
                vector_db = FAISS.from_documents(batch, embeddings)
            else:
                vector_db.add_documents(batch)
            
            print(f"Processed {min(i+batch_size, len(docs))}/{len(docs)} documents")
        
        # 最终保存
        save_path = Path(KB_DIR) / str(kb_id)
        vector_db.save_local(folder_path=str(save_path), index_name="index")
        
    except Exception as e:
        raise RuntimeError(f"Vector store build failed: {str(e)}")

def load_retrievers(kb_id, cur_kb, cur_vendor):
    """加载双检索器"""
    # 加载BM25
    bm25_path = Path(KB_DIR) / str(kb_id) / "bm25_index.json"
    with open(bm25_path, "r", encoding="utf-8") as f:
        bm25_data = json.load(f)
    
    bm25_docs = [
        Document(
            page_content=doc["page_content"],
            metadata=doc["metadata"]
        ) for doc in bm25_data["docs"]
    ]
    bm25_retriever = BM25Retriever.from_documents(bm25_docs)
    bm25_retriever.k = cur_kb["chunk_k"]
    # 加载向量检索器
    kb_path = Path(KB_DIR) / str(kb_id)
    embeddings = MyOpenAICompatibleEmbeddings(
        model=cur_kb["model"],
        api_key=cur_kb["api_key"],
        base_url=cur_kb["base_url"],
    )
    
    vector_db = FAISS.load_local(
        folder_path=str(kb_path),
        embeddings=embeddings,
        allow_dangerous_deserialization=True,
        index_name="index"  # 与保存时的默认名称一致
    )
    vector_retriever = vector_db.as_retriever(
        search_kwargs={"k": cur_kb["chunk_k"]}
    )
    return bm25_retriever, vector_retriever

def query_vector_store(query: str, kb_id, cur_kb, cur_vendor):
    """使用EnsembleRetriever的混合查询"""
    bm25_retriever, vector_retriever = load_retrievers(kb_id, cur_kb, cur_vendor)
    if "weight" not in cur_kb:
        cur_kb["weight"] = 0.5
    # 初始化混合检索器
    ensemble_retriever = EnsembleRetriever(
        retrievers=[bm25_retriever, vector_retriever],
        weights=[1 - cur_kb["weight"], cur_kb["weight"]],  # 权重配置
    )
    
    # 获取结果
    docs = ensemble_retriever.invoke(query)
    # 格式转换
    return [{
        "content": doc.page_content,
        "metadata": doc.metadata,
    } for doc in docs]


async def process_knowledge_base(kb_id):
    """异步处理知识库的完整流程"""
    # 加载配置
    settings = await load_settings()
    # 查找对应知识库配置
    cur_kb = None
    providerId = None
    for kb in settings["knowledgeBases"]:
        if kb["id"] == kb_id:
            cur_kb = kb
            providerId = kb["providerId"]
            break
    cur_vendor = None
    for provider in settings["modelProviders"]:
        if provider["id"] == providerId:
            cur_vendor = provider["vendor"]
            break
    
    if not cur_kb:
        raise ValueError(f"Knowledge base {kb_id} not found in settings")
    # 异步获取文件处理结果
    processed_results = await get_files_json(cur_kb["files"])
    
    # 分块处理文档
    chunks = chunk_documents(processed_results, cur_kb)
    
    # 构建向量存储
    build_vector_store(chunks, kb_id, cur_kb,cur_vendor)

    return "知识库处理完成"

async def query_knowledge_base(kb_id, query: str):
    """查询知识库"""
    # 加载配置
    settings = await load_settings()
    # 查找对应知识库配置
    cur_kb = None
    providerId = None
    for kb in settings["knowledgeBases"]:
        if kb["id"] == kb_id:
            cur_kb = kb
            providerId = kb["providerId"]
            break
    cur_vendor = None
    for provider in settings["modelProviders"]:
        if provider["id"] == providerId:
            cur_vendor = provider["vendor"]
            break
    
    if not cur_kb:
        return f"Knowledge base {kb_id} not found in settings"
    # 查询知识库
    results = query_vector_store(query,kb_id, cur_kb,cur_vendor)
    return results

async def rerank_knowledge_base(query: str , docs: List[Dict]) -> List[Dict]:
    settings = await load_settings()
    providerId = settings["KBSettings"]["selectedProvider"]
    cur_vendor = None
    for provider in settings["modelProviders"]:
        if provider["id"] == providerId:
            cur_vendor = provider["vendor"]
            break
    if cur_vendor == "jina":
        # 获取设置中的模型和参数（可从配置中扩展）
        jina_api_key = settings["KBSettings"]["api_key"]
        model_name = settings["KBSettings"]["model"]
        top_n = settings["KBSettings"]["top_n"]

        # 构建 documents 列表
        documents = [doc.get("content", "") for doc in docs]

        # 构建请求数据
        url = settings["KBSettings"]["base_url"] + "/rerank"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {jina_api_key}"
        }
        data = {
            "model": model_name,
            "query": query,
            "top_n": top_n,
            "documents": documents,
            "return_documents": False
        }

        # 发送请求
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json=data)
        
        if response.status_code != 200:
            raise Exception(f"Jina reranking failed: {response.text}")

        result = response.json()

        # 提取 rerank 后的顺序
        ranked_indices = [item['index'] for item in result.get('results', [])]
        ranked_docs = [docs[i] for i in ranked_indices]

        return ranked_docs
    elif cur_vendor == "Vllm":
        # 获取设置中的模型和参数（可从配置中扩展）
        model_name = settings["KBSettings"]["model"]
        top_n = settings["KBSettings"]["top_n"]

        # 构建 documents 列表
        documents = [doc.get("content", "") for doc in docs]

        # 构建请求数据
        url = settings["KBSettings"]["base_url"] + "/rerank"
        headers = {"accept": "application/json", "Content-Type": "application/json"}
        data = {
            "model": model_name,
            "query": query,
            "top_n": top_n,
            "documents": documents,
        }

        # 发送请求
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json=data)
        
        if response.status_code != 200:
            raise Exception(f"Vllm reranking failed: {response.text}")

        result = response.json()

        # 提取 rerank 后的顺序
        ranked_indices = [item['index'] for item in result.get('results', [])]
        ranked_docs = [docs[i] for i in ranked_indices]

        return ranked_docs
    else:
        return docs

kb_tool = {
    "type": "function",
    "function": {
        "name": "query_knowledge_base",
        "description": f"通过自然语言获取的对应ID的知识库信息。回答时，在回答的最下方给出信息来源。以链接的形式给出信息来源，格式为：[file_name](file_path)。file_path可以是外部资源，也可以是127.0.0.1上的资源。返回链接时，不要让()内出现空格",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "需要搜索的问题。",
                },
                "kb_id": {
                    "type": "string",
                    "description": "知识库的ID。"
                }
            },
            "required": ["kb_id","query"],
        },
    },
}

async def main():
    """示例用法"""
    try:
        # 示例参数
        kb_id = 1744547848224
        test_query = "什么是LLM party？"
        
        # 处理知识库并获取结果
        await process_knowledge_base(kb_id)
        results = await query_knowledge_base(kb_id, test_query)

        # 打印结果
        print(results)

        return results
    except Exception as e:
        print(f"处理过程中发生错误: {str(e)}")
        raise
if __name__ == "__main__":
    asyncio.run(main())