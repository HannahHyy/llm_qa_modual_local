# -*-coding: UTF-8 -*-
"""
    Author: haoxiaolin
    CreateTime: 2025/11/18 09:48
    Description: 
8个意图异步, embedding花费时间 1.4510986804962158
8个意图开启最多8个进程, embedding花费时间 3.5038907527923584
8意图整体一次requests, 直接embedding花费时间 1.0967159271240234
8意图整体当做list, embedding花费时间 1.1986422538757324
"""

import aiohttp
import asyncio
import time
from multiprocessing import Pool
import requests


class EmbeddingService:
    def __init__(self, embed_url):
        self.embed_url = embed_url

    async def get_embeddings_whole1(self, texts):
        embedding_start_time = time.time()
        async with aiohttp.ClientSession() as session:
            async with session.post(
                    self.embed_url,
                    json=texts,
                    timeout=aiohttp.ClientTimeout(total=30)  # 修改1: 使用正确的timeout格式
            ) as response:  # 修改2: 使用async with
                response.raise_for_status()
                result = await response.json()
                embeddings = result.get("embeddings", [])
                if not embeddings:
                    raise ValueError("Embedding服务返回空的embeddings")
                print(f"{len(texts)}意图整体当做list, embedding花费时间", time.time() - embedding_start_time)
                return embeddings

    async def get_embeddings_part(self, texts):
        embedding_start_time = time.time()

        async def fetch_embedding(session, text):
            async with session.post(  # 修改3: 使用async with
                    self.embed_url,
                    json=[text],
                    timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                response.raise_for_status()
                result = await response.json()
                embedding = result.get("embeddings")
                if embedding is None:
                    raise ValueError("Embedding服务返回空的embedding")
                return embedding[0]  # 修改4: 返回第一个元素以保持一致性

        async with aiohttp.ClientSession() as session:
            tasks = [fetch_embedding(session, text) for text in texts]
            embeddings = await asyncio.gather(*tasks)

        print(f"{len(texts)}个意图异步, embedding花费时间", time.time() - embedding_start_time)
        return embeddings

    def get_embeddings_multiprocess(self, texts):
        start_time = time.time()
        with Pool(min(len(texts), 8)) as pool:
            results = pool.map(self._get_single_embedding, texts)
        print(f"{len(texts)}个意图开启最多8个进程, embedding花费时间", time.time() - start_time)
        return results

    def _get_single_embedding(self, text):
        """同步获取单个文本的嵌入向量"""
        try:  # 修改5: 添加异常处理
            response = requests.post(
                self.embed_url,
                json=[text],
                timeout=30
            )
            response.raise_for_status()
            result = response.json()
            embedding = result.get("embeddings")
            if embedding is None:
                raise ValueError("Embedding服务返回空的embedding")
            return embedding[0]
        except Exception as e:
            print(f"获取embedding失败: {text}, 错误: {e}")
            raise

    def get_embeddings_whole2(self, texts):
        """同步获取单个文本的嵌入向量"""
        embedding_start_time = time.time()
        try:  # 修改5: 添加异常处理
            response = requests.post(
                self.embed_url,
                json=texts,
                timeout=30
            )
            response.raise_for_status()
            result = response.json()
            embedding = result.get("embeddings")
            if embedding is None:
                raise ValueError("Embedding服务返回空的embedding")
            print(f"{len(embedding)}意图整体一次requests, 直接embedding花费时间", time.time() - embedding_start_time)
            return embedding[0]
        except Exception as e:
            print(f"获取embedding失败: {texts}, 错误: {e}")
            raise


async def main():
    embedding_service = EmbeddingService('http://127.0.0.1:8000/embed')
    texts = ['信息安全技术网络安全等级保护测评要求', 
             '网络安全等级保护测评机构管理办法', 
             '请列出一级,二级等级保护系统对于边界防护的具体要求各是什么样的?在第一级等保系统中，我能否通过使用防火墙来实现边界防护？',
             '在等保一级系统中，对于防止用户越权访问敏感数据有哪些规定', 
             '在等保一级系统中，对于存在未防护的影子系统有哪些规定？', 
             '在等保一级系统中，对于存在未防护的影子系统有哪些规', 
             '你好你好你好', 
             '在等保二级系统中，对于存在未防护的影子系统有哪些规'
             ]
    await embedding_service.get_embeddings_part(texts)   # 异步
    embedding_service.get_embeddings_multiprocess(texts)  # 多进程
    embedding_service.get_embeddings_whole2(texts)       # 直接请求
    await embedding_service.get_embeddings_whole1(texts)  # 直接请求


if __name__ == "__main__":
    asyncio.run(main())