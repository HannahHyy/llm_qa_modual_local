import os
import sys
import time
from typing import Optional
import pymysql

MYSQL_HOST = "localhost"
MYSQL_PORT = int("3306")
MYSQL_DB   = "chatdb"
MYSQL_USER = "chatuser"
MYSQL_PASS = "ChangeMe123!"

RETRY_TIMES = 5
RETRY_BACKOFF_SEC = 2.0

# users表，存储用户基本信息，用于多用户会话隔离
DDL_USERS = """
CREATE TABLE IF NOT EXISTS users (
  user_id      VARCHAR(64)  NOT NULL PRIMARY KEY,
  username     VARCHAR(128),
  created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

# sessions表：存储会话信息
DDL_SESSIONS = """
CREATE TABLE IF NOT EXISTS sessions (
  session_id   VARCHAR(64)  NOT NULL PRIMARY KEY,
  user_id      VARCHAR(64)  NOT NULL,
  name         VARCHAR(255),
  created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  is_active    TINYINT DEFAULT 1,
  CONSTRAINT fk_sessions_user FOREIGN KEY (user_id) REFERENCES users(user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

DDL_IDX = [
    "CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);"
]

# session_archive_queue表：长期记忆归档的后台任务调度，当会话结束后，把任务放入队列中，异步归档
DDL_SESSION_ARCHIVE_QUEUE = """
CREATE TABLE IF NOT EXISTS session_archive_queue (
  id           BIGINT AUTO_INCREMENT PRIMARY KEY,
  user_id      VARCHAR(64) NOT NULL,
  session_id   VARCHAR(64) NOT NULL,
  status       ENUM('pending','processing','done','error') DEFAULT 'pending',
  scheduled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  error_msg    TEXT,
  UNIQUE KEY uq_archive_session (session_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

def connect_with_retry():
    last_err: Optional[Exception] = None
    for i in range(RETRY_TIMES):
        try:
            conn = pymysql.connect(
                host=MYSQL_HOST,
                port=MYSQL_PORT,
                user=MYSQL_USER,
                password=MYSQL_PASS,
                database=MYSQL_DB,
                charset="utf8mb4",
                autocommit=True,
            )
            return conn
        except Exception as e:
            last_err = e
            print(f"MySQL 连接失败({i+1}/{RETRY_TIMES})：{e}，{RETRY_BACKOFF_SEC}s后重试")
            time.sleep(RETRY_BACKOFF_SEC)
    raise last_err

def init_schema():
    conn = connect_with_retry()
    try:
        with conn.cursor() as cur:
            cur.execute(DDL_USERS)
            cur.execute(DDL_SESSIONS)
            for ddl in DDL_IDX:
                try:
                    cur.execute(ddl)
                except Exception:
                    pass
            cur.execute(DDL_SESSION_ARCHIVE_QUEUE)
        print("MySQL 表结构初始化完成。")
    finally:
        conn.close()

if __name__ == "__main__":
    init_schema()