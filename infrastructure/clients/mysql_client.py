"""
MySQL客户端

提供MySQL连接和操作的封装。
"""

from typing import Optional, List, Dict, Any, Tuple
import pymysql
from pymysql.cursors import DictCursor

from core.config import MySQLSettings
from core.exceptions import MySQLError
from core.logging import get_logger

logger = get_logger("MySQLClient")


class MySQLClient:
    """MySQL客户端类"""

    def __init__(self, settings: MySQLSettings):
        """
        初始化MySQL客户端

        Args:
            settings: MySQL配置
        """
        self.settings = settings
        self._connection: Optional[pymysql.Connection] = None

    def connect(self) -> None:
        """建立MySQL连接"""
        try:
            self._connection = pymysql.connect(
                host=self.settings.host,
                port=self.settings.port,
                user=self.settings.user,
                password=self.settings.password,
                database=self.settings.database,
                charset=self.settings.charset,
                autocommit=True,
                cursorclass=DictCursor,  # 使用字典游标
            )
            logger.info(f"MySQL连接成功: {self.settings.host}:{self.settings.port}/{self.settings.database}")
        except Exception as e:
            logger.error(f"MySQL连接失败: {e}")
            raise MySQLError(f"MySQL连接失败: {e}", details=str(e))

    def close(self) -> None:
        """关闭MySQL连接"""
        if self._connection:
            self._connection.close()
            logger.info("MySQL连接已关闭")

    def get_connection(self) -> pymysql.Connection:
        """
        获取MySQL连接实例

        Returns:
            MySQL连接实例

        Raises:
            MySQLError: 如果连接未初始化
        """
        if self._connection is None:
            raise MySQLError("MySQL连接未初始化，请先调用connect()")

        return self._connection

    # ==================== 查询操作 ====================

    def execute_query(
        self,
        sql: str,
        params: Optional[Tuple] = None
    ) -> List[Dict[str, Any]]:
        """
        执行查询SQL

        Args:
            sql: SQL语句
            params: 参数元组

        Returns:
            查询结果列表（字典格式）

        Raises:
            MySQLError: 查询失败
        """
        try:
            conn = self.get_connection()
            with conn.cursor() as cursor:
                cursor.execute(sql, params)
                result = cursor.fetchall()
                return result
        except Exception as e:
            logger.error(f"MySQL查询失败 sql={sql}: {e}")
            raise MySQLError(f"MySQL查询失败", details={"sql": sql, "error": str(e)})

    def execute_one(
        self,
        sql: str,
        params: Optional[Tuple] = None
    ) -> Optional[Dict[str, Any]]:
        """
        执行查询SQL并返回单条结果

        Args:
            sql: SQL语句
            params: 参数元组

        Returns:
            查询结果（字典格式），不存在返回None

        Raises:
            MySQLError: 查询失败
        """
        try:
            conn = self.get_connection()
            with conn.cursor() as cursor:
                cursor.execute(sql, params)
                result = cursor.fetchone()
                return result
        except Exception as e:
            logger.error(f"MySQL查询失败 sql={sql}: {e}")
            raise MySQLError(f"MySQL查询失败", details={"sql": sql, "error": str(e)})

    # ==================== 更新操作 ====================

    def execute_update(
        self,
        sql: str,
        params: Optional[Tuple] = None
    ) -> int:
        """
        执行更新SQL（INSERT、UPDATE、DELETE）

        Args:
            sql: SQL语句
            params: 参数元组

        Returns:
            影响的行数

        Raises:
            MySQLError: 更新失败
        """
        try:
            conn = self.get_connection()
            with conn.cursor() as cursor:
                affected_rows = cursor.execute(sql, params)
                return affected_rows
        except Exception as e:
            logger.error(f"MySQL更新失败 sql={sql}: {e}")
            raise MySQLError(f"MySQL更新失败", details={"sql": sql, "error": str(e)})

    def execute_many(
        self,
        sql: str,
        params_list: List[Tuple]
    ) -> int:
        """
        批量执行更新SQL

        Args:
            sql: SQL语句
            params_list: 参数元组列表

        Returns:
            影响的行数

        Raises:
            MySQLError: 更新失败
        """
        try:
            conn = self.get_connection()
            with conn.cursor() as cursor:
                affected_rows = cursor.executemany(sql, params_list)
                return affected_rows
        except Exception as e:
            logger.error(f"MySQL批量更新失败 sql={sql}: {e}")
            raise MySQLError(f"MySQL批量更新失败", details={"sql": sql, "error": str(e)})

    # ==================== 事务操作 ====================

    def begin_transaction(self) -> None:
        """开始事务"""
        try:
            conn = self.get_connection()
            conn.begin()
            logger.debug("MySQL事务已开始")
        except Exception as e:
            logger.error(f"MySQL开始事务失败: {e}")
            raise MySQLError(f"MySQL开始事务失败", details=str(e))

    def commit(self) -> None:
        """提交事务"""
        try:
            conn = self.get_connection()
            conn.commit()
            logger.debug("MySQL事务已提交")
        except Exception as e:
            logger.error(f"MySQL提交事务失败: {e}")
            raise MySQLError(f"MySQL提交事务失败", details=str(e))

    def rollback(self) -> None:
        """回滚事务"""
        try:
            conn = self.get_connection()
            conn.rollback()
            logger.debug("MySQL事务已回滚")
        except Exception as e:
            logger.error(f"MySQL回滚事务失败: {e}")
            raise MySQLError(f"MySQL回滚事务失败", details=str(e))

    # ==================== 便捷方法 ====================

    def insert_one(self, table: str, data: Dict[str, Any]) -> int:
        """
        插入单条记录

        Args:
            table: 表名
            data: 数据字典

        Returns:
            插入的ID

        Raises:
            MySQLError: 插入失败
        """
        columns = ", ".join(data.keys())
        placeholders = ", ".join(["%s"] * len(data))
        sql = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"

        try:
            conn = self.get_connection()
            with conn.cursor() as cursor:
                cursor.execute(sql, tuple(data.values()))
                return cursor.lastrowid
        except Exception as e:
            logger.error(f"MySQL插入失败 table={table}: {e}")
            raise MySQLError(f"MySQL插入失败", details={"table": table, "error": str(e)})

    def update_by_id(self, table: str, id_column: str, id_value: Any, data: Dict[str, Any]) -> int:
        """
        根据ID更新记录

        Args:
            table: 表名
            id_column: ID字段名
            id_value: ID值
            data: 更新数据字典

        Returns:
            影响的行数

        Raises:
            MySQLError: 更新失败
        """
        set_clause = ", ".join([f"{k} = %s" for k in data.keys()])
        sql = f"UPDATE {table} SET {set_clause} WHERE {id_column} = %s"
        params = tuple(data.values()) + (id_value,)

        return self.execute_update(sql, params)

    def delete_by_id(self, table: str, id_column: str, id_value: Any) -> int:
        """
        根据ID删除记录

        Args:
            table: 表名
            id_column: ID字段名
            id_value: ID值

        Returns:
            影响的行数

        Raises:
            MySQLError: 删除失败
        """
        sql = f"DELETE FROM {table} WHERE {id_column} = %s"
        return self.execute_update(sql, (id_value,))

    def select_by_id(self, table: str, id_column: str, id_value: Any) -> Optional[Dict[str, Any]]:
        """
        根据ID查询记录

        Args:
            table: 表名
            id_column: ID字段名
            id_value: ID值

        Returns:
            查询结果（字典格式），不存在返回None

        Raises:
            MySQLError: 查询失败
        """
        sql = f"SELECT * FROM {table} WHERE {id_column} = %s"
        return self.execute_one(sql, (id_value,))
