import chromadb
from rag import get_embedding
import uuid
class ChromaRetriever:
    def __init__(self,tenant:str,persist_dir:str="./chroma_data"):

        self.tenant=tenant

        client=chromadb.PersistentClient(persist_dir)

        self.collection=client.get_or_create_collection(
            name=f"{tenant}_chroma",
            metadata={"hnsw:space": "cosine"}
        )

    async def add_document(self,docs:list[str],redis_client):
        ids=[]
        embeddings=[]
        documents=[]
        for i,doc in  enumerate(docs):
            vcc=await get_embedding(doc,redis_client)
            embeddings.append(vcc)
            documents.append(doc)
            doc_id=f"{self.tenant}_{uuid.uuid4().hex}_{i}"
            ids.append(doc_id)
        self.collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=documents

        )

    async def retrieve(self,query:str,redis_client,top_k:int=3):
        query_vcc=await get_embedding(query,redis_client)
        results = self.collection.query(
            query_embeddings=[query_vcc],
            n_results=top_k,
            include=["documents", "distances"]
        )

        retrieved=[]
        if results["documents"] and results["documents"][0]: #列表和列表的第一个列表非空才继续执行，只存在0
            for doc,dis in zip(results["documents"][0],results["distances"][0]):
                similarity=1-dis
                retrieved.append((similarity,doc))
        return retrieved


