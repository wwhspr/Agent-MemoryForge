#!/usr/bin/env python3
"""
Neo4j数据库清空工具

neo4j 用你自己密码*
"""

try:
    from neo4j import GraphDatabase
    NEO4J_AVAILABLE = True
except ImportError:
    print("❌ Neo4j库未安装，请运行: pip install neo4j")
    NEO4J_AVAILABLE = False
    exit(1)

# Neo4j配置
NEO4J_CONFIG = {
    'uri': 'bolt://localhost:7687',
    'user': 'neo4j', 
    'password': '******'
}

def clear_neo4j():
    """清空Neo4j数据库"""
    try:
        print("🔵 正在连接Neo4j数据库...")
        driver = GraphDatabase.driver(
            NEO4J_CONFIG['uri'], 
            auth=(NEO4J_CONFIG['user'], NEO4J_CONFIG['password'])
        )
        driver.verify_connectivity()
        print("✅ Neo4j连接成功")
        
        with driver.session() as session:
            # 查询当前数据量
            result = session.run('MATCH (n) RETURN COUNT(n) as nodes')
            nodes_before = result.single()['nodes']
            
            result = session.run('MATCH ()-[r]->() RETURN COUNT(r) as relations')
            relations_before = result.single()['relations']
            
            print(f"📊 清空前: {nodes_before} 个节点, {relations_before} 个关系")
            
            if nodes_before > 0 or relations_before > 0:
                print("🗑️ 正在清空所有数据...")
                # 清空所有节点和关系
                session.run('MATCH (n) DETACH DELETE n')
                print("✅ Neo4j数据清空完成!")
            else:
                print("ℹ️ Neo4j数据库已经是空的")
            
            # 验证清空结果
            result = session.run('MATCH (n) RETURN COUNT(n) as nodes')
            nodes_after = result.single()['nodes']
            
            result = session.run('MATCH ()-[r]->() RETURN COUNT(r) as relations')
            relations_after = result.single()['relations']
            
            print(f"📊 清空后: {nodes_after} 个节点, {relations_after} 个关系")
        
        driver.close()
        return True
        
    except Exception as e:
        print(f"❌ Neo4j清空失败: {e}")
        return False

if __name__ == "__main__":
    clear_neo4j()
