# -*-coding: UTF-8 -*-
"""
    Author: haoxiaolin
    CreateTime: 2025/10/10 16:53
    Description: 
"""

import requests
from settings import config


def utils_embedding(params: list):
    embedding_info = config.EmbeddingConfig
    embedding_server_url = f"http://{embedding_info.host}:{embedding_info.port}{embedding_info.url}"
    print(embedding_server_url)
    # 绕过代理访问本地服务
    proxies = {
        'http': None,
        'https': None
    }
    response = requests.post(url=embedding_server_url, json=params, proxies=proxies)
    if response.status_code == 200:
        result = response.json()
        embeddings = result.get("embeddings", [])
        return embeddings
    else:
        return response.json()


if __name__ == '__main__':
    params = [
        "这是一个测试文本",
        "人工智能技术正在快速发展",
        "自然语言处理是AI的重要分支",
        "向量数据库在语义搜索中发挥重要作用"
    ]
    ret = utils_embedding(params)
    print(ret)