# -*-coding: UTF-8 -*-
"""
    Author: haoxiaolin
    CreateTime: 2025/11/1
    Description: JSON提取器类 - 从文本中智能提取JSON数据
"""

import json
import re
from typing import Optional, Union, Dict, List, Any


class JsonExtractor:
    """
    JSON提取器类
    
    提供多种方法从文本中提取JSON数据，支持：
    1. 从文本末尾提取JSON（主要方法）
    2. 通过正则表达式备用提取
    3. 通过标记位置提取（支持中文提示词）
    
    Attributes:
        default_markers: 默认的JSON标记列表
        default_value: 提取失败时的默认返回值
    """
    
    def __init__(
        self, 
        markers: Optional[List[str]] = None,
        default_value: Any = None
    ):
        """
        初始化JSON提取器
        
        Args:
            markers: JSON标记列表，用于通过标记位置提取JSON
                    如果为None，使用默认标记列表
            default_value: 提取失败时的默认返回值
        """
        self.default_markers = markers or [
            "json格式的解析结果：",
            "json格式：",
            "JSON格式：",
            "解析结果：",
            "结果：",
            "```json",
            "```",
        ]
        self.default_value = default_value
    
    def extract(self, text: str, default: Any = None) -> Union[Dict, List, Any]:
        """
        安全提取JSON（推荐方法）
        
        使用多种策略依次尝试提取JSON：
        1. 从文本末尾提取
        2. 通过标记位置提取
        
        Args:
            text: 包含JSON的文本
            default: 提取失败时的默认返回值，如果为None则使用初始化时的default_value
        
        Returns:
            dict或list: 解析后的JSON数据，失败返回default值
        """
        default = default if default is not None else self.default_value
        
        # 方法1: 从末尾提取
        result = self.extract_from_end(text)
        if result is not None:
            return result
        
        # 方法2: 通过标记提取
        result = self._try_extract_with_markers(text)
        if result is not None:
            return result
        
        return default
    
    def extract_from_end(self, text: str) -> Optional[Union[Dict, List]]:
        """
        从文本末尾提取JSON（主要方法）
        
        假设JSON总是在文本的最后部分，从后往前查找更高效
        
        Args:
            text: 包含JSON的文本
        
        Returns:
            dict或list: 解析后的JSON数据，失败返回None
        """
        if not text or not isinstance(text, str):
            return None

        # 移除末尾的空白字符
        text = text.rstrip()
        if not text:
            return None

        # JSON可能的结束字符
        json_end_chars = [']', '}']
        
        # 从末尾开始查找
        for end_char in json_end_chars:
            # 找到最后一个结束字符的位置
            end_idx = text.rfind(end_char)
            if end_idx == -1:
                continue

            # 找到对应的起始字符
            start_char = '[' if end_char == ']' else '{'
            
            # 从结束位置向前查找匹配的起始字符
            start_idx = self._match_brackets_backward(text, start_char, end_char, end_idx)
            
            if start_idx != -1:
                json_str = text[start_idx:end_idx + 1]
                try:
                    # 验证并解析JSON
                    json_data = json.loads(json_str)
                    return json_data
                except json.JSONDecodeError:
                    # 如果解析失败，继续尝试另一个结束字符
                    continue

        # 如果上面的方法都失败了，尝试更宽松的正则表达式
        return self._extract_json_fallback(text)
    
    def _match_brackets_backward(
        self, 
        text: str, 
        start_char: str, 
        end_char: str, 
        end_idx: int
    ) -> int:
        """
        从指定位置向前匹配括号，找到匹配的起始位置
        
        Args:
            text: 文本内容
            start_char: 起始字符 ('[' 或 '{')
            end_char: 结束字符 (']' 或 '}')
            end_idx: 结束字符的位置
        
        Returns:
            int: 匹配的起始位置，失败返回-1
        """
        bracket_count = 0
        in_string = False
        escape_next = False

        for i in range(end_idx, -1, -1):  # 从后往前遍历
            char = text[i]

            if escape_next:
                escape_next = False
                continue

            if char == '\\' and i > 0:
                # 检查前一个字符，判断是否是转义字符
                prev_char = text[i - 1]
                if prev_char != '\\':
                    escape_next = True
                continue

            # 处理字符串内的引号
            if char == '"':
                # 检查前面的字符，判断是否是转义引号
                if i > 0 and text[i - 1] == '\\':
                    # 需要检查是否是连续偶数个反斜杠（转义的转义）
                    backslash_count = 0
                    j = i - 1
                    while j >= 0 and text[j] == '\\':
                        backslash_count += 1
                        j -= 1
                    # 如果反斜杠数量是偶数，则是转义引号，不算字符串边界
                    if backslash_count % 2 == 0:
                        in_string = not in_string
                else:
                    in_string = not in_string
                continue

            # 只在非字符串区域处理括号
            if not in_string:
                if char == end_char:
                    bracket_count += 1
                elif char == start_char:
                    bracket_count -= 1
                    if bracket_count == 0:
                        return i

        return -1
    
    def _extract_json_fallback(self, text: str) -> Optional[Union[Dict, List]]:
        """
        备用方法：使用正则表达式从末尾提取JSON
        
        Args:
            text: 包含JSON的文本
        
        Returns:
            dict或list: 解析后的JSON数据，失败返回None
        """
        # 移除末尾空白
        text = text.rstrip()

        # 匹配JSON数组或对象（从末尾开始）
        patterns = [
            r'\[\s*\{.*?\}\s*\]\s*$',  # JSON数组格式
            r'\{.*?\}\s*$',  # JSON对象格式
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.DOTALL)
            if match:
                json_str = match.group(0).strip()
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError:
                    continue

        return None
    
    def _try_extract_with_markers(self, text: str) -> Optional[Union[Dict, List]]:
        """
        通过JSON标记位置提取（作为最后的备选方案）
        
        Args:
            text: 包含JSON的文本
        
        Returns:
            dict或list: 解析后的JSON数据，失败返回None
        """
        # 找到所有标记的位置
        marker_positions = []
        for marker in self.default_markers:
            # 查找所有出现位置，取最后一个
            last_pos = text.rfind(marker)
            if last_pos != -1:
                marker_positions.append((last_pos + len(marker), marker))

        if not marker_positions:
            return None

        # 取最靠后的标记位置
        marker_positions.sort(reverse=True)
        start_pos = marker_positions[0][0]
        remaining = text[start_pos:].strip()

        # 查找第一个JSON起始字符
        json_start_chars = {'[': ']', '{': '}'}

        for start_char, end_char in json_start_chars.items():
            start_idx = remaining.find(start_char)
            if start_idx == -1:
                continue

            # 使用标准方法匹配括号
            end_idx = self._match_brackets_forward(remaining, start_char, end_char, start_idx)
            if end_idx != -1:
                json_str = remaining[start_idx:end_idx + 1]
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError:
                    continue

        return None
    
    def _match_brackets_forward(
        self, 
        text: str, 
        start_char: str, 
        end_char: str, 
        start_idx: int
    ) -> int:
        """
        从指定位置向后匹配括号，找到匹配的结束位置
        
        Args:
            text: 文本内容
            start_char: 起始字符 ('[' 或 '{')
            end_char: 结束字符 (']' 或 '}')
            start_idx: 起始字符的位置
        
        Returns:
            int: 匹配的结束位置，失败返回-1
        """
        bracket_count = 0
        in_string = False
        escape_next = False

        for i in range(start_idx, len(text)):
            char = text[i]

            if escape_next:
                escape_next = False
                continue

            if char == '\\':
                escape_next = True
                continue

            if char == '"' and not escape_next:
                in_string = not in_string
                continue

            if not in_string:
                if char == start_char:
                    bracket_count += 1
                elif char == end_char:
                    bracket_count -= 1
                    if bracket_count == 0:
                        return i

        return -1


# 便捷函数：为了向后兼容，提供函数式接口
def extract_json_safe(text: str, default=None) -> Union[Dict, List, Any]:
    """
    便捷函数：安全提取JSON
    
    Args:
        text: 包含JSON的文本
        default: 提取失败时的默认返回值
    
    Returns:
        dict或list: 解析后的JSON数据
    """
    extractor = JsonExtractor()
    return extractor.extract(text, default)


def extract_json_from_end(text: str) -> Optional[Union[Dict, List]]:
    """
    便捷函数：从文本末尾提取JSON
    
    Args:
        text: 包含JSON的文本
    
    Returns:
        dict或list: 解析后的JSON数据，失败返回None
    """
    extractor = JsonExtractor()
    return extractor.extract_from_end(text)


# 测试代码
if __name__ == "__main__":
    ret = """1. 首先分析用户问题可以拆分成哪几个意图

用户的问题是"河北单位网络中计算机总数是多少? 服务器是多少台?"，这是一个相对明确的查询需求。根据专家分析和相关文档的参考，这个问题主要涉及统计河北单位网络中的终端设备数量。从查询目的来看，这是一个完整的统计查询，不需要进行意图拆分，可以作为一个单一的意图来处理。

2. 以流利的中文输出每个意图的具体含义{"name": test, "age": 18}

**意图：统计河北单位网络中的计算机和服务器数量**

- **识别到的节点类型**：`Unit`（单位节点）、`Netname`（网络名称节点）、`Terminaltype`（终端类型节点）。识别依据是用户问题中提到的"河北单位"对应`Unit`节点，"网络"对应`Netname`节点，"计算机"和"服务器"对应`Terminaltype`节点中的具体类型分类。

- **识别到的关系类型**：`UNIT_NET`（单位与网络的关系）、`TERMINAL_NET`（终端与网络的关系）。识别依据是专家分析和相关文档中的示例查询模式，这些关系用于连接单位、网络和终端设备，构建完整的查询路径。

- **具体含义**：该意图旨在查询河北单位所关联的网络中所有终端设备的数量，并分别统计其中计算机（通常指普通终端）和服务器的数量。查询会通过单位名称过滤出河北单位，然后遍历其关联的网络和终端设备，使用条件计数来区分不同类型的终端设备。

3.以下是json格式的解析结果：
[{"intent_item": "统计河北单位网络中的计算机和服务器数量", "cypher": "MATCH (u:Unit)-[:UNIT_NET]->(n:Netname)<-[:TERMINAL_NET]-(t:Terminaltype) WHERE u.name CONTAINS '河北单位' RETURN u.name AS unitName, n.name AS netName, COUNT(CASE WHEN t.name CONTAINS '终端' THEN t ELSE null END) AS totalComputers, COUNT(CASE WHEN t.name CONTAINS '服务器' THEN t ELSE null END) AS totalServers"}]"""

    # 测试类方法
    print("=" * 50)
    print("测试 JsonExtractor 类方法:")
    print("=" * 50)
    
    extractor = JsonExtractor()
    result = extractor.extract_from_end(ret)

    if result:
        print("✓ 提取成功!")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print(f"\n类型: {type(result).__name__}")
        if isinstance(result, list):
            print(f"列表长度: {len(result)}")
            print("\n列表项详情:")
            for idx, item in enumerate(result, 1):
                print(f"\n  项目 {idx}:")
                print(f"    intent_item: {item.get('intent_item', 'N/A')}")
                print(f"    cypher: {item.get('cypher', 'N/A')[:80]}...")
    else:
        print("✗ 提取失败，使用备用方法...")
        result = extractor.extract(ret)
        if result:
            print("✓ 备用方法提取成功!")
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print("✗ 所有方法都失败了")

    # 测试便捷函数
    print("\n" + "=" * 50)
    print("测试便捷函数:")
    print("=" * 50)
    
    result2 = extract_json_safe(ret)
    if result2:
        print("✓ 便捷函数提取成功!")
        print(f"类型: {type(result2).__name__}")

    # 测试边界情况
    print("\n" + "=" * 50)
    print("测试边界情况:")
    print("=" * 50)

    # 测试1: 空字符串
    assert extractor.extract("", default=[]) == []

    # 测试2: 只有JSON
    test2 = '[{"test": "value"}]'
    result2 = extractor.extract_from_end(test2)
    assert result2 is not None
    print("✓ 测试2通过: 纯JSON提取")

    # 测试3: 末尾有空白
    test3 = ret + "   \n\t  "
    result3 = extractor.extract_from_end(test3)
    assert result3 is not None
    print("✓ 测试3通过: 末尾空白处理")

    # 测试4: 自定义标记
    custom_extractor = JsonExtractor(
        markers=["自定义标记：", "json格式的解析结果："],
        default_value=[]
    )
    result4 = custom_extractor.extract(ret)
    assert result4 is not None
    print("✓ 测试4通过: 自定义标记")

    print("\n✓ 所有边界测试通过!")
