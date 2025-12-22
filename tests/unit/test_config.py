"""
配置管理单元测试
"""

import pytest
from core.config import Settings, get_settings, RedisSettings, MySQLSettings


class TestSettings:
    """Settings类测试"""

    def test_get_settings_singleton(self):
        """测试配置单例模式"""
        settings1 = get_settings()
        settings2 = get_settings()
        assert settings1 is settings2, "配置实例应该是单例"

    def test_redis_settings(self, settings):
        """测试Redis配置"""
        assert isinstance(settings.redis, RedisSettings)
        assert settings.redis.host is not None
        assert settings.redis.port > 0
        assert settings.redis.db >= 0

    def test_redis_url_generation(self, settings):
        """测试Redis URL生成"""
        url = settings.redis.url
        assert url.startswith("redis://")
        assert str(settings.redis.port) in url

    def test_mysql_settings(self, settings):
        """测试MySQL配置"""
        assert isinstance(settings.mysql, MySQLSettings)
        assert settings.mysql.host is not None
        assert settings.mysql.port > 0
        assert settings.mysql.database is not None

    def test_es_settings(self, settings):
        """测试ES配置"""
        assert settings.es.host is not None
        assert settings.es.port > 0
        assert settings.es.knowledge_index is not None
        assert settings.es.conversation_index is not None

    def test_es_url_generation(self, settings):
        """测试ES URL生成"""
        url = settings.es.url
        assert url.startswith("http://")
        assert str(settings.es.port) in url

    def test_es_auth_tuple(self, settings):
        """测试ES认证元组"""
        auth = settings.es.auth
        assert isinstance(auth, tuple)
        assert len(auth) == 2
        assert auth[0] == settings.es.username
        assert auth[1] == settings.es.password

    def test_system_settings(self, settings):
        """测试系统配置"""
        assert settings.system_prompt is not None
        assert settings.session_timeout_minutes > 0
        assert settings.log_level in ["DEBUG", "INFO", "WARNING", "ERROR"]
