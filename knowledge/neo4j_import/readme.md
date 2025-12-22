docker ps 
Neo4j已经成功启动了。让我测试一下连接: curl -f http://10.26.52.2:7474 
docker exec neo4j-local ls -la /var/lib/neo4j/import 
# 复制节点文件:
docker cp ./neo4j_import/node/. neo4j-local:/var/lib/neo4j/import/ 
# 复制关系文件：
docker cp ./neo4j_import/relation/. neo4j-local:/var/lib/neo4j/import/ 
# 检查文件复制情况：
docker exec neo4j-local ls -la /var/lib/neo4j/import 

现在我将使用cypher-shell来执行导入语句。首先执行节点导入。让我从Safeproduct节点开始：

combine_llm 终端

sudo docker exec neo4j-local cypher-shell -u neo4j -p "ChangeMe123!" -d neo4j --format plain "LOAD CSV WITH HEADERS FROM 'file:///Safeproduct.csv' AS row MERGE (a:Safeproduct { SP_ID:row.SP_ID, safeProductNo: row.safeProductNo, name: row.name, safeProductId: row.safeProductId, safeProductCount: row.safeProductCount, productType: row.productType });"

很好！现在继续导入Question节点：

combine_llm 终端

sudo docker exec neo4j-local cypher-shell -u neo4j -p "ChangeMe123!" -d neo4j --format plain "LOAD CSV WITH HEADERS FROM 'file:///question.csv' AS row MERGE (a:Question { questionId: row.question_id, questionIndex: row.question_index, questionContent: row.questionContent, questionNetCount: row.questionNetCount });"

继续导入SYSTEM节点：

combine_llm 终端

sudo docker exec neo4j-local cypher-shell -u neo4j -p "ChangeMe123!" -d neo4j --format plain "LOAD CSV WITH HEADERS FROM 'file:///SYSTEM.csv' AS row MERGE (a:SYSTEM { systemId: row.systemId, name: row.name, systemSecretLevel: row.systemSecretLevel });"

导入NetName节点：

combine_llm 终端

sudo docker exec neo4j-local cypher-shell -u neo4j -p "ChangeMe123!" -d neo4j --format plain "LOAD CSV WITH HEADERS FROM 'file:///netName.csv' AS row MERGE (a:Netname { netId: row.netid, networkType: row.networkType, name: row.name });"

导入Unit节点：

combine_llm 终端

sudo docker exec neo4j-local cypher-shell -u neo4j -p "ChangeMe123!" -d neo4j --format plain "LOAD CSV WITH HEADERS FROM 'file:///Unit.csv' AS row MERGE (a:Unit { unitId: row.unitId, unitType: row.unitType, name: row.name, unitArea: row.unitArea, unitRegion: row.unitRegion });"

导入Totalintegrations节点：

combine_llm 终端

sudo docker exec neo4j-local cypher-shell -u neo4j -p "ChangeMe123!" -d neo4j --format plain "LOAD CSV WITH HEADERS FROM 'file:///totalintergration.csv' AS row MERGE (a:Totalintegrations { totalIntegrationId: row.overallintergrationUnit_id, name: row.name, totalIntegrationLevel: row.totalIntergrationLevel, totalIntegrationNo: row.totalIntergrationNo, validatedateend: row.validatedateend });"

最后导入Terminaltype节点：

combine_llm 终端

sudo docker exec neo4j-local cypher-shell -u neo4j -p "ChangeMe123!" -d neo4j --format plain "LOAD CSV WITH HEADERS FROM 'file:///Terminaltype.csv' AS row MERGE (a:Terminaltype { name:row.name, terminalTypeId: row.terminalTypeId, terminalSum: row.terminalSum });"

很好！所有节点都已成功导入。现在让我完成第三个任务并开始第四个任务（导入关系）：

现在开始导入关系。首先导入UNIT_NET关系：

combine_llm 终端

sudo docker exec neo4j-local cypher-shell -u neo4j -p "ChangeMe123!" -d neo4j --format plain "LOAD CSV WITH HEADERS FROM 'file:///UNIT_NET.csv' AS row MATCH (a:Unit{unitId: row.UNITID}) MATCH (b:Netname{netId: row.NETID}) MERGE (a)-[:UNIT_NET]->(b);"

导入QUESTIONNET关系：

combine_llm 终端

sudo docker exec neo4j-local cypher-shell -u neo4j -p "ChangeMe123!" -d neo4j --format plain "LOAD CSV WITH HEADERS FROM 'file:///net_question.csv' AS row MATCH (a:Question{questionId: row.question_id}) MATCH (b:Netname{netId: row.net_id}) MERGE (a)-[:QUESTIONNET]->(b);"

导入SECURITY_NET关系：

combine_llm 终端

sudo docker exec neo4j-local cypher-shell -u neo4j -p "ChangeMe123!" -d neo4j --format plain "LOAD CSV WITH HEADERS FROM 'file:///SECURITY_NET.csv' AS row MATCH (a:Safeproduct{SP_ID: row.SPID}) MATCH (b:Netname{netId: row.NETID}) MERGE (a)-[:SECURITY_NET]->(b);"

导入OVERUNIT_NET关系（totalintegration_net）：

combine_llm 终端

sudo docker exec neo4j-local cypher-shell -u neo4j -p "ChangeMe123!" -d neo4j --format plain "LOAD CSV WITH HEADERS FROM 'file:///net_totaolintergration.csv' AS row MATCH (a:Totalintegrations{totalIntegrationId: row.overintergrationunit_id}) MATCH (b:Netname{netId: row.net_id}) MERGE (a)-[:OVERUNIT_NET]->(b);"

导入SYSTEM_NET关系：

combine_llm 终端

sudo docker exec neo4j-local cypher-shell -u neo4j -p "ChangeMe123!" -d neo4j --format plain "LOAD CSV WITH HEADERS FROM 'file:///SYSTEM_NET.csv' AS row MATCH (a:SYSTEM{systemId: row.sysID}) MATCH (b:Netname{netId: row.NETID}) MERGE (a)-[:SYSTEM_NET]->(b);"

最后导入OPERATIONUNIT_NET关系：

combine_llm 终端

sudo docker exec neo4j-local cypher-shell -u neo4j -p "ChangeMe123!" -d neo4j --format plain "LOAD CSV WITH HEADERS FROM 'file:///OPERATIONUNIT_NET.csv' AS row MATCH (a:Totalintegrations{totalIntegrationId: row.t_id}) MATCH (b:Netname{netId: row.net_id}) MERGE (a)-[:OPERATIONUNIT_NET]->(b);"