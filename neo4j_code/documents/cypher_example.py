cypher_example = [
    {
        "question": "防火墙配置策略粗",
        "cypher_query": """
            MATCH (q: Question {questionContent: '防火墙配置策略粗'})-[:QUESTIONNET]->(net: Netname)<-[:UNIT_NET]-(u: Unit)
            WITH u.unitRegion AS unitRegion, COLLECT(DISTINCT net.name) AS networks
            WITH unitRegion, networks, SIZE(networks) AS totalNetworks 
            ORDER BY totalNetworks DESC 
            RETURN collect({unitRegion: unitRegion, sampleNetworks: networks[0..10], totalNetworks: totalNetworks}) 
            AS netInfos 
        """
    },
    {
        "question": "河北单位建设了哪些网络?",
        "cypher_query": """
            MATCH (u:Unit)-[:UNIT_NET]->(n:Netname)
            where u.name CONTAINS "河北单位"
            RETURN n.netId AS netId, n.networkType AS networkType, n.name AS netName
        """
    },
    {
            "question": "河北单位网络中计算机总数是多少? 服务器是多少台?",
            "cypher_query": """
                MATCH (u:Unit)-[:UNIT_NET]->(n:Netname)<-[:TERMINAL_NET]-(t:Terminaltype)
                WHERE u.name CONTAINS "北京单位"
                RETURN 
                    u.name AS unitName,
                    n.name as netName,
                    COUNT(CASE WHEN t.name CONTAINS '终端' THEN t ELSE null END) AS totalTerminals,
                    COUNT(CASE WHEN t.name CONTAINS '服务器' THEN t ELSE null END) AS totalServers
            """
        },
    {
            "question": "哪些单位/网络采用了防火墙? 列举出来",
            "cypher_query": """
                MATCH (u:Unit)-[:UNIT_NET]->(n:Netname)<-[:SECURITY_NET]-(s:Safeproduct)
                where s.name CONTAINS "防火墙"
                RETURN 
                    u.name AS unitName,
                    n.netId AS netId,
                    n.name AS netName,
                    s.name AS productName,
                    s.productType AS productType
            """
        },
]