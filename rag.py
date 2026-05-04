from contextlib import asynccontextmanager
import httpx
from fastapi import FastAPI, HTTPException, status,UploadFile,File
from pydantic import BaseModel
import os
from dotenv import load_dotenv
from pypdf import PdfReader
import tempfile
from zhipuai import ZhipuAI
import numpy as np
import hashlib,json


""" 
标准RAG集成流程：
离线阶段（文档预处理，通常在应用启动时或上传文档时执行一次）
1.文本传入：接收文档（如上传的 .txt/.pdf）

2.分割：将长文本切分成小块（chunks）

3.向量化：对每个 chunk 调用 Embedding API，生成向量并存储（例如存到列表或向量数据库）
 在线阶段（用户每次提问时执行）
1.用户提问：接收查询字符串。

2.向量化查询：将查询文本转成向量（使用同样的 Embedding 模型）。

3.计算余弦相似度：遍历存储的所有文档向量，计算与查询向量的相似度，找出 top-k 最相关的 chunk。

4.构建提示词：将检索到的 chunk 与原始问题一起拼接到提示模板中。

5.调用大模型 API：发送提示词，获取生成回答。

6.输出回答：返回给客户端。
"""
"""RAG核心"""

load_dotenv()#从根目录.env读取环境变量并加载到python里面
client=ZhipuAI(api_key=os.getenv("ZHIPUAI_API_KEY"))  #使用SDK,直接调用封装好的方法

async def get_embedding(text:str,redis_client,model:str="embedding-3",dimensions:int=1024)->list:
    key=hashlib.md5(text.encode()).hexdigest()   #对相同文本生成固定哈希
    try:
        cached=await redis_client.get(key)
        if cached:
            return json.loads(cached)
    except Exception as e:
        # 日志记录 Redis 错误，继续调用 API
        print(f"Redis error: {e}")

    response=client.embeddings.create(
        model=model,
        input=text,
        dimensions=dimensions    #向量维度
    )
    vec=response.data[0].embedding
    try:
        await redis_client.setex(key, 86400, json.dumps(vec))  #缓存一天  永久可以用set
    except Exception as e:
        print(f"Redis error: {e}")
    return vec   #向量
"""被chromadb取代了
class SimpleVectorRetriever:

    def __init__(self):
        self.documents=[]
        self.vectors=[]

    def add_document(self,docs):
        for doc in docs:
            vec=get_embedding(doc)
            self.documents.append(doc)
            self.vectors.append(vec)

    def retrieve(self,query:str,top_k:int=3):
        query_vec=get_embedding(query)
        scores=[]
        for vec in self.vectors:
            sim=cosine_similarity(query_vec,vec)
            scores.append(sim)
        top=np.argsort(scores)[-top_k:][::-1]   #返回数值升序排列的索引，取后top_k个，再倒序，这样top[0]就是余弦相似度最大的索引了
        results=[(scores[i],self.documents[i]) for i in top]
        return results
"""
"""余弦相似度"""
def cosine_similarity(vec_a:list[float],vec_b:list[float])->float:
    a=np.array(vec_a,dtype=np.float32)  #变成数组
    b=np.array(vec_b,dtype=np.float32)
    dot=np.dot(a,b)                      #点积
    norm_a=float(np.linalg.norm(a))
    norm_b=float(np.linalg.norm(b))            #模长
    if norm_a==0.0 or norm_b==0.0:
        return 0.0

    return float(dot/(norm_a*norm_b))
"""提示词构造"""
def build_rag_prompt(query: str, retrieved_docs: list) -> str:
    prompt=f"请基于以下信息回答\n\n【检索到的相关信息】"
    for i ,(score,doc) in enumerate(retrieved_docs):
        prompt +=f"{i+1}.{doc}\n"
    prompt += f"\n【用户提问】\n{query}\n请给出你的回答。"
    return prompt



"""文本传入和简单分割"""
def load_txt(file_path:str)->str:
    with open(file_path , "r", encoding="utf-8") as f:
        return f.read()

def load_pdf(file_path:str)->str:
    reader=PdfReader(file_path)
    text=""
    for page in reader.pages:    #遍历每一个页面
        text+=page.extract_text()#转化为纯文本（表格，图片，格式丢失）
    return text
#字数分割，部分重叠
def split_txt(text:str,chunk_size:int=500,overlap:int=50)->list[str]:
    chunks=[]
    start=0
    text_len=len(text)

    while start<text_len:
        end=min(start+chunk_size,text_len)
        chunks.append(text[start:end])

        if end==text_len:
            break
        start=end-overlap

        if  start<=0:
            break

    return chunks

def process_document(file_path:str)->list[str]:
    if file_path.endswith(".txt"):
        text=load_txt(file_path)
    elif file_path.endswith(".pdf"):
        text=load_pdf(file_path)
    else:
        raise ValueError("只支持.txt or .pdf")
    chunks=split_txt(text)
    return chunks





