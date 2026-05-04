from contextlib import asynccontextmanager
import httpx
from fastapi import FastAPI, HTTPException, status,UploadFile,File,Depends
from pydantic import BaseModel
import os
from dotenv import load_dotenv
from pypdf import PdfReader
import tempfile
from zhipuai import ZhipuAI
import numpy as np
from rag import get_embedding, cosine_similarity,  split_txt, process_document, build_rag_prompt
from db import init_db,save_message,get_history
import uuid #用于生成随机用户id
from core import get_current_tenant
from chroma_retriever import ChromaRetriever
import redis.asyncio as redis
from fastapi.staticfiles import StaticFiles


"""RAG核心"""
class ChatRequest(BaseModel):    #pydantic的一个基类，可以自动检测传入的数据（不合格会报错），把传入的各种数据变成对应的python对象
    prompt: str                  #提示词
    max_tokens: int = 1024       #告诉模型回答最多多少token
    session_id: str | None = None      #用户不同窗口隔离

"""简单调用api，使用 raw HTTP，自己手写 HTTP 请求"""


# 从环境变量读取配置
ZHIPUAI_API_KEY = os.getenv("ZHIPUAI_API_KEY")
ZHIPUAI_BASE_URL = os.getenv("ZHIPUAI_BASE_URL", "https://open.bigmodel.cn/api/paas/v4")

# 启动时检查 API Key 是否存在
if not ZHIPUAI_API_KEY:
    raise RuntimeError("请在 .env 文件中设置 ZHIPUAI_API_KEY")

@asynccontextmanager    #让你可以用 async with 语句来管理资源的获取和释放，在进入代码块时执行初始化，在退出时执行清理
async def lifespan(apps: FastAPI): #异步函数,这里的apps就是app
    init_db()
    async with httpx.AsyncClient(timeout=120.0) as clients:   #是一个 异步 HTTP 客户端的实例,用于发送HTTP请求
        apps.state.httpx_client = clients  #client是临时创建的，为了在函数外使用它，而不是反复创建浪费时间，httpx_client是变量名，用的时候要a=apps.state.httpx_client
        apps.state.redis= await redis.from_url("redis://localhost:6379",decode_responses=True) #根据url,创建客户端链接对象，TRUE自动将 Redis 返回的 bytes 转为 str

        yield   #运行到这里停止，结束后运行下面的，lient.aclose() 自动被调用，释放网络连接
        await apps.state.redis.close()  #关闭连接池

app = FastAPI(lifespan=lifespan)
retrievers={}


# ... 创建 app 之后
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.post("/chat")

async def chat_endpoint(request: ChatRequest,tenant:str=Depends(get_current_tenant)):
    if tenant not in retrievers:
        raise HTTPException(status_code=400,detail="请先在upload传入知识库")

    retriever=retrievers[tenant]
    redis_client=app.state.redis
    req_session_id=request.session_id
    if  req_session_id is None:
        req_session_id=uuid.uuid4().hex #生成一个随机的 UUID（通用唯一标识符）对象,将该对象转换为 32 位十六进制字符串
    history=get_history(tenant,req_session_id)
    messages = []
    for role, content in history:
        messages.append({"role": role, "content": content})

    retrieved_docs=await retriever.retrieve(request.prompt,redis_client)  #寻找索引
    prompt=build_rag_prompt(request.prompt,retrieved_docs)   #构造提示词
    messages.append({"role": "user", "content": prompt})
    # 正确拼接 URL
    url = f"{ZHIPUAI_BASE_URL}/chat/completions"
    #请求头：携带元信息，描述请求的附加属性
    headers = {
        "Authorization": f"Bearer {ZHIPUAI_API_KEY}",
        "Content-Type": "application/json" #数据类型
    }
    # 请求体：携带实际数据，通常用于 POST、PUT 等需要向服务器提交信息的请求。
    payload = {
        "model": "glm-5.1",   # 或者 "glm-4" 等
        "messages": messages,
        "max_tokens": request.max_tokens
    }

    try:
        response = await app.state.httpx_client.post(url, headers=headers, json=payload)
        response.raise_for_status()        #检查状态码是否为2xx，不然就抛出异常
        result = response.json()   #json变成字典，json.dump(),反过来
        answer = result["choices"][0]["message"]["content"]
        save_message(tenant,req_session_id,"user",request.prompt)
        save_message(tenant,req_session_id,"assistant",answer)
        return {"response": answer,"session_id": req_session_id}
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="大模型服务响应超时")   #推理太久了，延迟高，时间不够
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=f"大模型服务错误: {str(e)}") #请求不合格
    except httpx.RequestError as e:
        raise HTTPException(status_code=503, detail=f"调用大模型服务失败: {str(e)}")  #网络

"""处理传入的文件"""

@app.post("/upload")
async def upload(file: UploadFile = File(...),tenant:str=Depends(get_current_tenant)):
    filename = file.filename  #上传文件的原始文件名
    if not (filename.endswith(".txt") or filename.endswith(".pdf")):
      raise HTTPException(status_code=400,detail="文件格式错误")

    suffix=os.path.splitext(filename)[1] #将文件名拆分，[1]是扩展名（.txt .pdf)
    with tempfile.NamedTemporaryFile(delete=False,suffix=suffix) as tmp:  #创建临时文件，False(不会自动删除）
        content=await file.read()
        tmp.write(content)
        tmp_path=tmp.name   #获取文件路径（直接tmp.name也可以，这里是防止后面被覆盖）

    try:
        if tenant not in retrievers:
            retrievers[tenant]=ChromaRetriever(tenant)
        retriever=retrievers[tenant]
        chunks=process_document(tmp_path)
        redis_client = app.state.redis
        await retriever.add_document(chunks,redis_client)
        return {
        "filename": filename,
        "total_chunks": len(chunks),
        "return":"文件保存成功"
           }
    except ValueError as e:
        raise HTTPException(status_code=400,detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500,detail=str(e))
    finally:
        os.remove(tmp_path)   #删除文件



