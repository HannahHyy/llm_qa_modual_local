"""
配置管理模块

使用Pydantic Settings进行类型安全的配置管理，支持从环境变量和.env文件读取配置。
"""

import os
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class RedisSettings(BaseSettings):
    """Redis配置"""

    host: str = Field(default="localhost", description="Redis主机地址")
    port: int = Field(default=6379, description="Redis端口")
    db: int = Field(default=0, description="Redis数据库编号")
    password: Optional[str] = Field(default=None, description="Redis密码")
    enabled: bool = Field(default=True, description="是否启用Redis")

    model_config = SettingsConfigDict(
        env_prefix="REDIS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @property
    def url(self) -> str:
        """生成Redis连接URL"""
        if self.password:
            return f"redis://:{self.password}@{self.host}:{self.port}/{self.db}"
        return f"redis://{self.host}:{self.port}/{self.db}"


class MySQLSettings(BaseSettings):
    """MySQL配置"""

    host: str = Field(default="localhost", description="MySQL主机地址")
    port: int = Field(default=3306, description="MySQL端口")
    user: str = Field(default="chatuser", description="MySQL用户名")
    password: str = Field(default="ChangeMe123!", description="MySQL密码")
    database: str = Field(default="chatdb", description="MySQL数据库名")
    charset: str = Field(default="utf8mb4", description="字符集")

    model_config = SettingsConfigDict(
        env_prefix="MYSQL_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


class ESSettings(BaseSettings):
    """Elasticsearch配置"""

    host: str = Field(default="localhost", description="ES主机地址")
    port: int = Field(default=9200, description="ES端口")
    username: str = Field(default="elastic", description="ES用户名")
    password: str = Field(default="password01", description="ES密码")
    knowledge_index: str = Field(default="kb_vector_store", description="知识库索引名")
    conversation_index: str = Field(default="conversation_history", description="会话历史索引名")
    timeout: int = Field(default=30, description="请求超时时间（秒）")

    model_config = SettingsConfigDict(
        env_prefix="ES_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @property
    def url(self) -> str:
        """生成ES连接URL"""
        return f"http://{self.host}:{self.port}"

    @property
    def auth(self) -> tuple:
        """生成ES认证元组"""
        return (self.username, self.password)


class Neo4jSettings(BaseSettings):
    """Neo4j配置"""

    uri: str = Field(default="bolt://localhost:7687", description="Neo4j连接URI")
    user: str = Field(default="neo4j", description="Neo4j用户名")
    password: str = Field(default="ChangeMe123!", description="Neo4j密码")
    enabled: bool = Field(default=True, description="是否启用Neo4j")

    model_config = SettingsConfigDict(
        env_prefix="NEO4J_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


class LLMSettings(BaseSettings):
    """LLM配置"""

    base_url: str = Field(
        default="https://dashscope.aliyuncs.com/compatible-mode/v1",
        description="LLM API基础URL"
    )
    api_key: str = Field(default="", description="LLM API密钥")
    model_name: str = Field(default="qwen-plus", description="LLM模型名称")
    timeout: int = Field(default=120, description="请求超时时间（秒）")
    max_retries: int = Field(default=3, description="最大重试次数")

    model_config = SettingsConfigDict(
        env_prefix="LLM_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


class EmbeddingSettings(BaseSettings):
    """Embedding配置"""

    base_url: str = Field(default="http://localhost:8000", description="Embedding服务URL")
    model_name: str = Field(default="bge-large-zh", description="Embedding模型名称")
    timeout: int = Field(default=30, description="请求超时时间（秒）")

    model_config = SettingsConfigDict(
        env_prefix="EMBEDDING_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


class Settings(BaseSettings):
    """主配置类，聚合所有子配置"""

    # 系统配置
    system_prompt: str = Field(
        default="你是一个有帮助的中文网络等级保护智能助手，请用简洁、清晰的方式回答。",
        description="系统提示词"
    )
    session_timeout_minutes: int = Field(default=300, description="会话超时时间（分钟）")

    # 功能开关
    knowledge_matching_enabled: bool = Field(default=True, description="是否启用知识匹配")
    intent_parser_enabled: bool = Field(default=True, description="是否启用意图解析")
    knowledge_retrieval_enabled: bool = Field(default=True, description="是否启用知识检索")

    # 日志配置
    log_level: str = Field(default="INFO", description="日志级别")
    log_file_path: str = Field(default="logs/app.log", description="日志文件路径")
    log_rotation: str = Field(default="500 MB", description="日志文件轮转大小")
    log_retention: str = Field(default="10 days", description="日志保留时间")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # 子配置实例
    redis: RedisSettings = Field(default_factory=RedisSettings)
    mysql: MySQLSettings = Field(default_factory=MySQLSettings)
    es: ESSettings = Field(default_factory=ESSettings)
    neo4j: Neo4jSettings = Field(default_factory=Neo4jSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    embedding: EmbeddingSettings = Field(default_factory=EmbeddingSettings)


# 全局配置实例（单例模式）
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """
    获取全局配置实例（单例模式）

    Returns:
        Settings: 配置实例
    """
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
