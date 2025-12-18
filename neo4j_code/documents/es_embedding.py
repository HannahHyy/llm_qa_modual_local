# -*-coding: UTF-8 -*-
"""
    Author: haoxiaolin
    CreateTime: 2025/11/4 09:42
    Description: 优化后的ES问答系统，支持向量相似度搜索
"""
from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk
import json
import sys
import os
import requests
from typing import List, Dict, Optional

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from documents.cypher_example import cypher_example
from settings.config import EmbeddingConfig, EsConfig


class QASearchEngine:
    def __init__(self, hosts=None, timeout=3600):
        """
        初始化 Elasticsearch 连接
        :param hosts: Elasticsearch 服务器地址列表，如果为None则使用配置文件中的地址
        :param timeout: 请求超时时间
        """
        # 如果没有提供hosts，使用配置文件中的地址
        if hosts is None:
            # 从配置中获取ES地址
            es_url = EsConfig.ES_BASE_URL
            hosts = [es_url]

        # 从配置中获取ES用户名和密码
        es_username = EsConfig.ES_USERNAME
        es_password = EsConfig.ES_PASSWORD

        # 处理hosts格式：elasticsearch-py 9.x 需要完整URL格式
        # 参考 test_es_delete.py 的用法，直接使用完整URL
        formatted_hosts = []
        for host in hosts:
            # 如果已经是完整URL，直接使用
            if host.startswith('http://') or host.startswith('https://'):
                formatted_hosts.append(host)
            else:
                # 如果不是完整URL，添加http://前缀
                formatted_hosts.append(f'http://{host}')

        print(f"🔗 连接配置: hosts={formatted_hosts}, username={es_username}")

        # 临时禁用代理（针对本地ES连接）
        old_http_proxy = os.environ.get('HTTP_PROXY')
        old_https_proxy = os.environ.get('HTTPS_PROXY')
        old_http_proxy_lower = os.environ.get('http_proxy')
        old_https_proxy_lower = os.environ.get('https_proxy')

        # 移除代理设置
        os.environ.pop('HTTP_PROXY', None)
        os.environ.pop('HTTPS_PROXY', None)
        os.environ.pop('http_proxy', None)
        os.environ.pop('https_proxy', None)

        try:
            # 创建 Elasticsearch 客户端连接（带认证）
            # elasticsearch-py 9.x 使用 basic_auth 参数
            # 注意：hosts 参数应该接收列表，每个元素是完整URL
            self.es = Elasticsearch(
                hosts=formatted_hosts,
                basic_auth=(es_username, es_password),
                request_timeout=timeout,
                max_retries=3,
                retry_on_timeout=True
            )

            # 测试连接
            print("🔄 正在测试连接...")
            ping_result = self.es.ping()
            if ping_result:
                print("✅ 成功连接到 Elasticsearch")
            else:
                print("❌ 无法连接到 Elasticsearch (ping返回False)")
                raise Exception("连接失败")
        finally:
            # 恢复代理设置
            if old_http_proxy:
                os.environ['HTTP_PROXY'] = old_http_proxy
            if old_https_proxy:
                os.environ['HTTPS_PROXY'] = old_https_proxy
            if old_http_proxy_lower:
                os.environ['http_proxy'] = old_http_proxy_lower
            if old_https_proxy_lower:
                os.environ['https_proxy'] = old_https_proxy_lower

        
        # Embedding配置
        self.embed_url = EmbeddingConfig.BGE_URL
        self.embedding_dim = 1024  # BGE模型向量维度
        
        self.index_name = None

    def _get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        调用embedding服务获取向量
        :param texts: 文本列表
        :return: 向量列表
        """
        try:
            # 绕过代理访问本地服务
            proxies = {
                'http': None,
                'https': None
            }
            response = requests.post(
                self.embed_url,
                json=texts,
                timeout=EmbeddingConfig.REQUEST_TIMEOUT,
                proxies=proxies
            )
            response.raise_for_status()
            result = response.json()
            embeddings = result.get("embeddings", [])
            if not embeddings:
                raise ValueError("Embedding服务返回空的embeddings")
            return embeddings
        except Exception as e:
            print(f"❌ Embedding服务调用失败: {e}")
            raise

    def create_qa_index(self, index_name="qa_system"):
        """
        创建问答系统索引，包含向量字段
        :param index_name: 索引名称
        """
        # 索引映射配置（不使用扩展分词器，使用ES默认分词器）
        mapping = {
            "settings": {
                "number_of_shards": 1,  # 分片数
                "number_of_replicas": 1  # 副本数
                # 不配置 analysis，使用ES默认分词器
            },
            "mappings": {
                "properties": {
                    "question": {
                        "type": "text",
                        # 不指定 analyzer 和 search_analyzer，使用ES默认的 standard analyzer
                        "fields": {
                            "keyword": {
                                "type": "keyword"
                            }
                        }
                    },
                    "answer": {
                        "type": "text"
                        # 不指定 analyzer 和 search_analyzer，使用ES默认的 standard analyzer
                    },
                    "embedding_question": {
                        "type": "dense_vector",
                        "dims": self.embedding_dim,
                        "index": True,
                        "similarity": "cosine"
                    }
                }
            }
        }

        try:
            # 检查索引是否存在
            if not self.es.indices.exists(index=index_name):
                # 创建索引
                self.es.indices.create(index=index_name, body=mapping)
                print(f"✅ 成功创建索引: {index_name}")
            else:
                print(f"ℹ️  索引已存在: {index_name}")

            self.index_name = index_name
            return True

        except Exception as e:
            print(f"❌ 创建索引失败: {e}")
            return False

    def load_data_from_cypher_example(self) -> List[Dict]:
        """
        从cypher_example.py读取数据
        :return: 问答对列表
        """
        qa_list = []
        for item in cypher_example:
            qa_list.append({
                "question": item.get("question", ""),
                "answer": item.get("cypher_query", "")
            })
        print(f"✅ 从cypher_example.py读取到 {len(qa_list)} 条数据")
        return qa_list

    def bulk_add_qa_pairs(self, qa_list: List[Dict]):
        """
        批量添加问答对，自动生成embedding_question
        :param qa_list: 问答对列表，格式: [{"question": "Q1", "answer": "A1"}, ...]
        """
        if not qa_list:
            print("⚠️  问答对列表为空")
            return 0, []

        # 批量获取所有问题的embedding
        questions = [qa.get("question", "") for qa in qa_list]
        print(f"📝 正在获取 {len(questions)} 个问题的embedding...")
        
        try:
            # 批量获取embedding
            embeddings = self._get_embeddings(questions)
            print(f"✅ 成功获取 {len(embeddings)} 个embedding向量")
        except Exception as e:
            print(f"❌ 获取embedding失败: {e}")
            return 0, [str(e)]

        # 构建批量操作
        actions = []
        for i, qa in enumerate(qa_list):
            if i < len(embeddings):
                action = {
                    "_index": self.index_name,
                    "_source": {
                        "question": qa.get("question", ""),
                        "answer": qa.get("answer", ""),
                        "embedding_question": embeddings[i]
                    }
                }
                actions.append(action)

        try:
            success_count, errors = bulk(self.es, actions)
            print(f"✅ 批量添加成功: {success_count} 条")
            if errors:
                print(f"⚠️  部分失败: {len(errors)} 条")
                for error in errors[:5]:  # 只显示前5个错误
                    print(f"   错误: {error}")
            return success_count, errors
        except Exception as e:
            print(f"❌ 批量添加失败: {e}")
            return 0, [str(e)]

    def delete_all_documents(self):
        """
        删除索引中的所有文档
        """
        try:
            if not self.index_name:
                print("❌ 索引名称未设置")
                return False
            
            # 使用delete_by_query删除所有文档
            query = {
                "query": {
                    "match_all": {}
                }
            }
            result = self.es.delete_by_query(index=self.index_name, body=query)
            deleted_count = result.get("deleted", 0)
            print(f"✅ 成功删除 {deleted_count} 条文档")
            return True
        except Exception as e:
            print(f"❌ 删除文档失败: {e}")
            return False

    def vector_similarity_search(self, query: str, top_k: int = 5, min_score: float = 0.0):
        """
        向量相似度搜索
        :param query: 用户查询问题
        :param top_k: 返回结果数量
        :param min_score: 最小相似度分数阈值
        :return: 搜索结果列表
        """
        try:
            # 获取查询问题的embedding
            query_embeddings = self._get_embeddings([query])
            query_vector = query_embeddings[0]

            # 构建向量搜索查询
            search_body = {
                "query": {
                    "script_score": {
                        "query": {"match_all": {}},
                        "script": {
                            "source": "cosineSimilarity(params.query_vector, 'embedding_question') + 1.0",
                            "params": {"query_vector": query_vector}
                        }
                    }
                },
                "size": top_k,
                "min_score": min_score + 1.0  # 因为cosineSimilarity返回[-1,1]，+1后变成[0,2]
            }

            results = self.es.search(index=self.index_name, body=search_body)
            
            # 格式化结果
            formatted_results = []
            for hit in results['hits']['hits']:
                score = hit['_score'] - 1.0  # 还原为[-1,1]范围的相似度
                formatted_result = {
                    'id': hit['_id'],
                    'score': score,
                    'question': hit['_source']['question'],
                    'answer': hit['_source']['answer']
                }
                formatted_results.append(formatted_result)

            return {
                'total': results['hits']['total']['value'],
                'max_score': results['hits']['max_score'] - 1.0 if results['hits']['max_score'] else 0.0,
                'results': formatted_results
            }
        except Exception as e:
            print(f"❌ 向量搜索失败: {e}")
            return {
                'total': 0,
                'max_score': 0.0,
                'results': []
            }

    def get_index_stats(self):
        """获取索引统计信息"""
        try:
            if not self.index_name:
                return {}
            stats = self.es.indices.stats(index=self.index_name)
            count = self.es.count(index=self.index_name)
            return {
                'doc_count': count['count'],
                'index_size': stats['_all']['total']['store']['size_in_bytes']
            }
        except Exception as e:
            print(f"❌ 获取统计信息失败: {e}")
            return {}

    def delete_index(self):
        """删除索引（谨慎使用）"""
        try:
            if not self.index_name:
                print("❌ 索引名称未设置")
                return False
            self.es.indices.delete(index=self.index_name)
            print(f"✅ 已删除索引: {self.index_name}")
            return True
        except Exception as e:
            print(f"❌ 删除索引失败: {e}")
            return False


# ==================== 功能实现 ====================

def function1_load_data_to_es(index_name: str = "qa_system"):
    """
    功能1: 从cypher_example.py读取数据并存入ES
    :param index_name: ES索引名称
    """
    print("\n" + "="*60)
    print("功能1: 从cypher_example.py读取数据并存入ES")
    print("="*60)
    
    # 初始化搜索引擎（使用配置文件中的ES地址）
    search_engine = QASearchEngine()
    
    # 创建索引
    search_engine.create_qa_index(index_name)
    
    # 从cypher_example.py读取数据
    qa_list = search_engine.load_data_from_cypher_example()
    
    # 批量添加到ES
    print("\n📝 开始批量添加数据到ES...")
    success_count, errors = search_engine.bulk_add_qa_pairs(qa_list)
    
    # 显示统计信息
    stats = search_engine.get_index_stats()
    print(f"\n📊 索引统计: {stats}")
    
    return search_engine


def function2_reload_data(index_name: str = "qa_system"):
    """
    功能2: 删除功能1写入的ES数据，重新执行功能1
    :param index_name: ES索引名称
    """
    print("\n" + "="*60)
    print("功能2: 删除功能1写入的ES数据，重新执行功能1")
    print("="*60)
    
    # 初始化搜索引擎（使用配置文件中的ES地址）
    search_engine = QASearchEngine()
    search_engine.index_name = index_name
    
    # 删除所有文档
    print("\n🗑️  删除索引中的所有文档...")
    search_engine.delete_all_documents()
    
    # 重新执行功能1
    print("\n🔄 重新加载数据...")
    qa_list = search_engine.load_data_from_cypher_example()
    success_count, errors = search_engine.bulk_add_qa_pairs(qa_list)
    
    # 显示统计信息
    stats = search_engine.get_index_stats()
    print(f"\n📊 索引统计: {stats}")
    
    return search_engine


def function3_search_question(query: str, top_k: int = 5, index_name: str = "qa_system"):
    """
    功能3: 传入一个问题，将问题embedding，然后和embedding_question做相似度对比，取top
    :param query: 查询问题
    :param top_k: 返回top K个结果
    :param index_name: ES索引名称
    :return: 搜索结果
    """
    print("\n" + "="*60)
    print(f"功能3: 向量相似度搜索 - 查询: '{query}'")
    print("="*60)
    
    # 初始化搜索引擎（使用配置文件中的ES地址）
    search_engine = QASearchEngine()
    search_engine.index_name = index_name
    
    # 执行向量搜索
    results = search_engine.vector_similarity_search(query, top_k=top_k)
    
    # 显示结果
    print(f"\n找到 {results['total']} 个相关结果 (最大相似度: {results['max_score']:.4f}):")
    print("-" * 60)
    print(type(results), results)
    # for i, result in enumerate(results['results'], 1):
    #     print(f"\n{i}. [相似度: {result['score']:.4f}]")
    #     print(f"   问题: {result['question']}")
    #     # print(f"   答案: {result['answer'][:100]}..." if len(result['answer']) > 100 else f"   答案: {result['answer']}")
    #     print(f"答案: {result['answer']}")
    return results


def test_es_connection():
    """测试ES连接"""
    print("="*60)
    print("测试ES连接")
    print("="*60)
    
    try:
        from settings.config import EsConfig
        import requests
        
        es_url = EsConfig.ES_BASE_URL
        es_username = EsConfig.ES_USERNAME
        es_password = EsConfig.ES_PASSWORD
        
        print(f"ES地址: {es_url}")
        print(f"用户名: {es_username}")
        print(f"密码: {es_password}")
        
        # 使用requests直接测试连接
        print("\n使用requests测试连接...")
        try:
            response = requests.get(
                f"{es_url}/_cluster/health",
                auth=(es_username, es_password),
                timeout=5
            )
            if response.status_code == 200:
                print("✅ requests连接成功!")
                print(f"   响应: {response.json()}")
            else:
                print(f"❌ requests连接失败: 状态码 {response.status_code}")
                print(f"   响应: {response.text}")
        except Exception as e:
            print(f"❌ requests连接异常: {e}")
        
        # 使用Elasticsearch客户端测试
        print("\n使用Elasticsearch客户端测试连接...")
        search_engine = QASearchEngine()
        print("✅ Elasticsearch客户端连接成功!")
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


def main():
    """主函数演示用法"""
    print("="*60)
    print("ES问答系统 - 向量相似度搜索演示")
    print("="*60)
    
    index_name = "qa_system"
    
    # 功能1: 从cypher_example.py读取数据并存入ES
    # search_engine = function1_load_data_to_es(index_name)
    
    # 功能2: 删除数据并重新加载（可选，取消注释以执行）
    # function2_reload_data(index_name)
    
    # 功能3: 向量相似度搜索示例
    test_queries = [
        # "资质单位运行维护的涉密网",
        # "北京太极",
        # "防火墙配置策略",
        # "资质过期"
        "哪些单位/网络采用了防火墙?",
        "北京单位网络应用系统有多少个? 不同密级分布数量是多少?"
    ]
    
    print("\n" + "="*60)
    print("功能3: 向量相似度搜索演示")
    print("="*60)
    
    for query in test_queries:
        function3_search_question(query, top_k=1, index_name=index_name)
        print("\n")


if __name__ == "__main__":
    # test_es_connection()  # 先测试连
    main()
