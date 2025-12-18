
# -*-coding: UTF-8 -*-
"""
    Author: haoxiaolin
    CreateTime: 2025/10/8 23:51
    Description:
        配置文件
"""

class RedisConfig:
    # host: str = "114.115.150.85"
    host: str = "127.0.0.1"
    port: int = 6379
    db: int = 1


class Neo4jConfig:
    # ip: str = "192.168.100.137"
    ip: str = "127.0.0.1"
    user: str = "neo4j"
    password: str = "ChangeMe123!"
    # uri: str = f"bolt://{ip}:17687"
    uri: str = f"bolt://{ip}:7687"


class LlmConfig:
    # IP_PORT = "https://192.168.100.121:8880"
    # base_url = IP_PORT + "/v1"
    # key = "EMPTY"
    # model_name = "QwQ-32B"

    # test
    IP_PORT = "https://192.168.100.121:8880"
    base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    key = "sk-f9f3209599454a49ba6fb4f36c3c0434"
    model_name = "deepseek-v3"

    APPID = ""
    SecretKey = ""
    USERID = "5"

    TOKEN = ""
    TOKEN_WG = None
    TMP_TEST_DIGEST = ""


class EsConfig:
    ES_BASE_URL = "http://127.0.0.1:9200"
    ES_USERNAME = "elastic"
    ES_PASSWORD = "password01"
    ES_KNOWLEDGE_INDEX = "kb_vector_store"
    ES_CONVERSATION_INDEX = "conversation_history"
    REQUEST_TIMEOUT = 30.0


class EmbeddingConfig:
    SERVER_IP = "127.0.0.1"  # 改为你的远程服务器IP
    BGE_PORT = "8000"
    BGE_URL = f"http://{SERVER_IP}:{BGE_PORT}/embed"
    BGE_HEALTH_URL = f"http://{SERVER_IP}:{BGE_PORT}/health"
    REQUEST_TIMEOUT = 30.0
