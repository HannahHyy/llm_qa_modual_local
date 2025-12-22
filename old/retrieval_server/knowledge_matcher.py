"""
知识匹配模块 - 简化版本，专门比较embedding_content和LLM输出的相似度
"""
import jieba
import numpy as np
from typing import List, Tuple, Dict, Any
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

def preprocess_text(text: str) -> str:
    """预处理文本"""
    if not text:
        return ""
    # 使用jieba分词
    words = jieba.cut(text)
    return " ".join(words)

def match_query_with_embeddings_tfidf(query: str, embedding_contents: List[str], top_k: int = 20) -> List[Tuple[float, str]]:
    """
    使用TF-IDF计算相似度
    
    Args:
        query: 查询文本
        embedding_contents: embedding内容列表
        top_k: 返回top k结果
        
    Returns:
        List[Tuple[float, str]]: [(分数, embedding_content), ...]
    """
    if not query.strip() or not embedding_contents:
        return [(0.0, content) for content in embedding_contents[:top_k]]
    
    # 预处理文本
    processed_query = preprocess_text(query)
    processed_contents = [preprocess_text(content) for content in embedding_contents]
    
    # 构建语料库
    corpus = [processed_query] + processed_contents
    
    # 计算TF-IDF
    vectorizer = TfidfVectorizer(
        max_features=5000,
        ngram_range=(1, 2),
        min_df=1,
        max_df=0.95
    )
    
    tfidf_matrix = vectorizer.fit_transform(corpus)
    
    # 计算相似度
    query_vector = tfidf_matrix[0:1]
    content_vectors = tfidf_matrix[1:]
    
    similarities = cosine_similarity(query_vector, content_vectors)[0]
    
    # 组合结果
    results = [(float(sim), content) for sim, content in zip(similarities, embedding_contents)]
    
    # 按分数降序排序并返回top k
    results.sort(key=lambda x: x[0], reverse=True)
    return results[:top_k]

# 如果安装了rank_bm25库，可以使用BM25
try:
    from rank_bm25 import BM25Okapi
    
    def match_query_with_embeddings_bm25(query: str, embedding_contents: List[str], top_k: int = 20) -> List[Tuple[float, str]]:
        """
        使用BM25计算相似度
        
        Args:
            query: 查询文本
            embedding_contents: embedding内容列表
            top_k: 返回top k结果
            
        Returns:
            List[Tuple[float, str]]: [(分数, embedding_content), ...]
        """
        if not query.strip() or not embedding_contents:
            return [(0.0, content) for content in embedding_contents[:top_k]]
        
        # 预处理文本
        processed_query = list(jieba.cut(query))
        processed_contents = [list(jieba.cut(content)) for content in embedding_contents]
        
        # 构建BM25模型
        bm25 = BM25Okapi(processed_contents)
        
        # 计算分数
        scores = bm25.get_scores(processed_query)
        
        # 组合结果
        results = [(float(score), content) for score, content in zip(scores, embedding_contents)]
        
        # 按分数降序排序并返回top k
        results.sort(key=lambda x: x[0], reverse=True)
        return results[:top_k]
    
    # 默认使用BM25
    def match_query_with_embeddings(query: str, embedding_contents: List[str], top_k: int = 20) -> List[Tuple[float, str]]:
        return match_query_with_embeddings_bm25(query, embedding_contents, top_k)
    
except ImportError:
    # 如果没有安装rank_bm25，使用TF-IDF
    def match_query_with_embeddings(query: str, embedding_contents: List[str], top_k: int = 20) -> List[Tuple[float, str]]:
        return match_query_with_embeddings_tfidf(query, embedding_contents, top_k)

async def match_and_format_knowledge(
    llm_output: str, 
    knowledge_results: List[Dict[str, Any]], 
    similarity_threshold: float = 0.0,  # 不再使用阈值，改为返回top_k
    max_results: int = 20  # 改为返回top 20
) -> List[str]:
    """
    匹配知识并返回结果列表，适配server2.py的调用方式
    
    Args:
        llm_output: LLM的完整输出文本
        knowledge_results: 知识检索结果列表，每个元素包含embedding_content字段
        similarity_threshold: 相似度阈值（已废弃，保留兼容性）
        max_results: 最大返回结果数量，默认20
        
    Returns:
        List[str]: 匹配的知识结果列表，每个元素是一条搜索结果
    """
    if not llm_output.strip() or not knowledge_results:
        return []
    
    # 提取所有embedding_content
    embedding_contents = []
    for item in knowledge_results:
        embedding_content = item.get("embedding_content", "")
        if embedding_content.strip():
            embedding_contents.append(embedding_content)
    
    if not embedding_contents:
        return []
    
    # 使用当前的匹配算法计算相似度
    results = match_query_with_embeddings(llm_output, embedding_contents, top_k=max_results)
    
    # 返回匹配结果列表，每个元素是一条搜索结果
    matched_results = []
    for score, content in results:
        matched_results.append(content.strip())
    
    return matched_results

# 测试代码
if __name__ == "__main__":
    # 测试数据
    query = """一级等级保护系统中实现边界隔离，需满足《GB/T 22239-2019》和《GB/T 28448-2019》的要求，具体方法及产品如下：

### **一、实现边界隔离的方法**

1. **部署边界防护设备**
   - 在网络边界（如内网与外网之间）部署访问控制设备（如防火墙、路由器等），确保所有跨边界的数据通信必须通过这些设备的受控接口进行。
   - **关键要求**：
     - 设备需配置安全策略，指定允许通信的端口，并启用策略（如防火墙规则）。
     - 禁止存在未受控的端口或路径（如非法无线接入点）。

2. **配置与核查**
   - **设备配置核查**：确认边界设备已开启访问控制功能，并明确指定允许的通信端口及策略。
   - **技术手段检测**：通过扫描或定位工具（如无线网络检测设备）排查未授权的边界连接。"""

    embedding_contents = [
        "标准：信息安全技术网络安全等级保护测评要求GB/T 28448-2019 的章节部分 6 第一级测评要求-6.1 安全测评通用要求-6.1.3 安全区域边界-6.1.3.1 边界防护 的具体内容如下：6.1.3.1 边界防护 6.1.3.1.1 测评单元（L1-ABS1-01） 该测评单元包括以下要求： a）测评指标：应保证跨越边界的访问和数据流通过边界设备提供的受控接口进行通信。b）测评对象：网闸、防火墙、路由器、交换机和无线接入网关设备等提供访问控制功能的设备或相关组件。c）测评实施包括以下内容：1）应核查在网络边界处是否部署访问控制设备；2）应核查设备配置信息是否指定端口进行跨越边界的网络通信，指定端口是否配置并启用了安全策略；3）应采用其他技术手段(如非法无线网络设备定位、核查设备配置信息等)核查是否不存在其他未受控端口进行跨越边界的网络通信。d）单元判定：如果1)~3)均为肯定，则符合本测评单元指标要求，否则不符合或部分符合本测评单元指标要求。",
        "标准：信息安全技术网络安全等级保护基本要求GB/T 22239-2019 的章节部分 6 第一级安全要求-6.1 安全通用要求-6.1.3 安全区域边界-6.1.3.1 边界防护 的具体内容如下：6.1.3.1 边界防护 应保证跨越边界的访问和数据流通过边界设备提供的受控接口进行通信。"
    ]
    
    # 模拟knowledge_results格式
    test_knowledge_results = [
        {"embedding_content": embedding_contents[0]},
        # {"embedding_content": embedding_contents[1]}
    ]
    
    print("=== 测试 match_and_format_knowledge 函数 ===\n")
    
    import asyncio
    
    async def test_async():
        result = await match_and_format_knowledge(query, test_knowledge_results, max_results=20)
        print(f"返回结果类型: {type(result)}")
        print(f"结果数量: {len(result)}")
        for i, item in enumerate(result, 1):
            print(f"结果 {i}: {item[:100]}...")
    
    asyncio.run(test_async())
    
    print("\n=== 测试 match_query_with_embeddings 函数 ===\n")
    
    results = match_query_with_embeddings(query, embedding_contents, top_k=20)
    
    # 显示结果
    for i, (score, content) in enumerate(results, 1):
        print(f"Embedding {i}:")
        print(f"  分数: {score:.4f}")
        print(f"  内容: {content[:100]}...")
        print()
    
    print(f"总共返回 {len(results)} 个结果")