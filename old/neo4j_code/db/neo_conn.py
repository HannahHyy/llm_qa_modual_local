# -*-coding: UTF-8 -*-
"""
    Author: haoxiaolin
    CreateTime: 2025/5/9 17:08
    Description: 
"""

from neo4j import GraphDatabase
from fastapi import Request


class Neo4jConnection:
    def __init__(self, uri, user, password):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self):
        if self.driver:
            self.driver.close()

    def query(self, query, parameters=None):
        try:
            with self.driver.session() as session:
                result = session.run(query, parameters)
                return [dict(record) for record in result]
        except Exception as e:
            print(f"Error executing query: {e}")
            return None

    def driver(self):
        return self.driver

    def execute_query(self, query):
        with self.driver.session() as session:
            result = session.run(query)
            return str(result.data())


async def get_neo4j(request: Request):
    """获取 Redis 连接的依赖项"""
    return request.app.state.neo4j