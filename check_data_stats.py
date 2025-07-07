#!/usr/bin/env python3
"""
数据统计查看器 - Data Statistics Viewer
=========================================

用于快速查看所有数据库中的数据量统计
包括: Redis, SQLite, Faiss, Neo4j, 文件系统

使用方法:
python check_data_stats.py

neo4j 用你自己密码*
"""

import redis
import sqlite3
import faiss
import json
import os
import sys
from datetime import datetime

# 尝试导入Neo4j，如果失败则设置为None
try:
    from neo4j import GraphDatabase
    NEO4J_AVAILABLE = True
except ImportError:
    GraphDatabase = None
    NEO4J_AVAILABLE = False

# 配置信息
REDIS_CONFIG = {'host': 'localhost', 'port': 6379, 'db': 0}
SQLITE_DB = 'ltm.db'
NEO4J_CONFIG = {
    'uri': 'bolt://localhost:7687',
    'user': 'neo4j', 
    'password': '*****'
}
VECTOR_INDEX_FILE = 'vector_index.faiss'
VECTOR_MAPPING_FILE = 'vector_mapping.json'
SKILLS_DIR = 'skills'

def print_header():
    """打印统计头部信息"""
    print("=" * 60)
    print("📊 Agent记忆系统数据统计报告")
    print(f"⏰ 统计时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

def check_redis_data():
    """检查Redis数据"""
    try:
        redis_client = redis.Redis(**REDIS_CONFIG, decode_responses=True)
        redis_client.ping()
        
        # STM 对话数据统计
        stm_keys = redis_client.keys('stm:conversation:*')
        stm_conversation_count = 0
        stm_summary_count = 0
        
        # 分类处理不同类型的STM key
        conversation_keys = [k for k in stm_keys if not k.endswith(':summaries')]
        summary_keys = [k for k in stm_keys if k.endswith(':summaries')]
        
        # 统计对话数据
        for key in conversation_keys:
            try:
                # 检查数据类型
                key_type = redis_client.type(key)
                if key_type == 'string':
                    data = redis_client.get(key)
                    if data:
                        try:
                            conv_data = json.loads(data)
                            stm_conversation_count += 1
                        except json.JSONDecodeError:
                            stm_conversation_count += 1  # 非JSON数据也算一个对话
                elif key_type == 'list':
                    length = redis_client.llen(key)
                    if length > 0:
                        stm_conversation_count += 1
                elif key_type == 'hash':
                    fields = redis_client.hlen(key)
                    if fields > 0:
                        stm_conversation_count += 1
            except Exception:
                # 静默处理错误，避免干扰统计
                continue
        
        # 统计摘要数据
        for key in summary_keys:
            try:
                key_type = redis_client.type(key)
                if key_type == 'hash':
                    stm_summary_count += redis_client.hlen(key)
                elif key_type == 'list':
                    stm_summary_count += redis_client.llen(key)
                elif key_type == 'string':
                    data = redis_client.get(key)
                    if data:
                        try:
                            summary_data = json.loads(data)
                            if isinstance(summary_data, list):
                                stm_summary_count += len(summary_data)
                            else:
                                stm_summary_count += 1
                        except json.JSONDecodeError:
                            stm_summary_count += 1
            except Exception:
                continue
        
        # WM 工作任务数据
        wm_keys = redis_client.keys('wm:task:*')
        wm_valid_tasks = 0
        task_types = {}
        task_status = {}
        
        for key in wm_keys:
            try:
                key_type = redis_client.type(key)
                if key_type == 'string':
                    data = redis_client.get(key)
                    if data:
                        try:
                            task_data = json.loads(data)
                            if isinstance(task_data, dict):
                                wm_valid_tasks += 1
                                task_type = task_data.get('task_type', 'unknown')
                                status = task_data.get('status', 'unknown')
                                task_types[task_type] = task_types.get(task_type, 0) + 1
                                task_status[status] = task_status.get(status, 0) + 1
                        except json.JSONDecodeError:
                            wm_valid_tasks += 1
                            task_types['unknown'] = task_types.get('unknown', 0) + 1
                            task_status['unknown'] = task_status.get('unknown', 0) + 1
            except Exception:
                continue
        
        print(f'🔴 Redis存储统计:')
        print(f'  � STM短期记忆:')
        print(f'    - 对话记录: {stm_conversation_count} 个')
        print(f'    - 对话摘要: {stm_summary_count} 条')
        
        print(f'  🔄 WM工作记忆:')
        print(f'    - 有效任务: {wm_valid_tasks} 个 (总key: {len(wm_keys)})')
        if task_types:
            print(f'    - 任务类型: {dict(list(task_types.items())[:3])}{"..." if len(task_types) > 3 else ""}')
        if task_status:
            print(f'    - 任务状态: {dict(list(task_status.items())[:3])}{"..." if len(task_status) > 3 else ""}')
        
        return {
            'status': 'success',
            'stm_conversations': stm_conversation_count,
            'stm_summaries': stm_summary_count,
            'wm_tasks': wm_valid_tasks
        }
        
    except Exception as e:
        print(f'❌ Redis连接失败: {e}')
        return {'status': 'error', 'error': str(e)}

def check_sqlite_data():
    """检查SQLite数据"""
    try:
        if not os.path.exists(SQLITE_DB):
            print(f'⚠️ SQLite数据库文件 {SQLITE_DB} 不存在')
            return {'status': 'error', 'error': 'Database file not found'}
        
        conn = sqlite3.connect(SQLITE_DB)
        cursor = conn.cursor()
        
        # 检查表是否存在
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        
        results = {}
        
        # LTM偏好数据 (旧表)
        if 'preferences' in tables:
            cursor.execute('SELECT COUNT(*) FROM preferences')
            prefs_count = cursor.fetchone()[0]
            
            # 统计用户分布
            cursor.execute('SELECT user_id, COUNT(*) FROM preferences GROUP BY user_id')
            user_prefs = dict(cursor.fetchall())
            results['old_preferences'] = {'count': prefs_count, 'users': user_prefs}
        else:
            results['old_preferences'] = {'count': 0, 'users': {}}
        
        # LTM偏好数据 (新表)
        if 'ltm_preferences' in tables:
            cursor.execute('SELECT COUNT(*) FROM ltm_preferences')
            ltm_prefs_count = cursor.fetchone()[0]
            
            cursor.execute('SELECT user_id, COUNT(*) FROM ltm_preferences GROUP BY user_id')
            ltm_user_prefs = dict(cursor.fetchall())
            results['new_preferences'] = {'count': ltm_prefs_count, 'users': ltm_user_prefs}
        else:
            results['new_preferences'] = {'count': 0, 'users': {}}
        
        # 向量元数据
        if 'vector_metadata' in tables:
            cursor.execute('SELECT COUNT(*) FROM vector_metadata')
            vector_meta_count = cursor.fetchone()[0]
            
            # 按类型统计
            cursor.execute('SELECT memory_type, COUNT(*) FROM vector_metadata GROUP BY memory_type')
            memory_types = dict(cursor.fetchall())
            results['vector_metadata'] = {'count': vector_meta_count, 'types': memory_types}
        else:
            results['vector_metadata'] = {'count': 0, 'types': {}}
        
        # 获取文件大小
        file_size = os.path.getsize(SQLITE_DB)
        size_mb = file_size / (1024 * 1024)
        
        print(f'🟡 SQLite存储统计 ({SQLITE_DB} - {size_mb:.2f}MB):')
        print(f'  📋 数据表: {len(tables)} 个 ({", ".join(tables)})')
        print(f'  ⚙️ LTM偏好设置:')
        print(f'    - 旧表(preferences): {results["old_preferences"]["count"]} 条')
        print(f'    - 新表(ltm_preferences): {results["new_preferences"]["count"]} 条')
        if results['new_preferences']['users']:
            print(f'    - 用户分布: {dict(list(results["new_preferences"]["users"].items())[:3])}{"..." if len(results["new_preferences"]["users"]) > 3 else ""}')
        
        print(f'  💾 向量元数据: {results["vector_metadata"]["count"]} 条')
        if results['vector_metadata']['types']:
            print(f'    - 类型分布: {results["vector_metadata"]["types"]}')
        
        conn.close()
        return {'status': 'success', **results, 'file_size_mb': size_mb}
        
    except Exception as e:
        print(f'❌ SQLite统计失败: {e}')
        return {'status': 'error', 'error': str(e)}

def check_faiss_data():
    """检查Faiss向量数据"""
    try:
        results = {}
        
        # 检查向量索引文件
        if os.path.exists(VECTOR_INDEX_FILE):
            index = faiss.read_index(VECTOR_INDEX_FILE)
            vector_count = index.ntotal
            vector_dim = index.d
            
            # 文件大小
            file_size = os.path.getsize(VECTOR_INDEX_FILE)
            size_kb = file_size / 1024
            
            results['index'] = {
                'count': vector_count,
                'dimension': vector_dim,
                'size_kb': size_kb
            }
        else:
            results['index'] = {'count': 0, 'dimension': 0, 'size_kb': 0}
        
        # 检查映射文件
        if os.path.exists(VECTOR_MAPPING_FILE):
            with open(VECTOR_MAPPING_FILE, 'r') as f:
                mapping_data = json.load(f)
                mapping_count = len(mapping_data)
                
                # 文件大小
                file_size = os.path.getsize(VECTOR_MAPPING_FILE)
                size_kb = file_size / 1024
                
                results['mapping'] = {
                    'count': mapping_count,
                    'size_kb': size_kb,
                    'format': 'new' if 'ids' in mapping_data else 'old'
                }
        else:
            results['mapping'] = {'count': 0, 'size_kb': 0, 'format': 'none'}
        
        print(f'🟢 Faiss向量存储统计:')
        if results['index']['count'] > 0:
            print(f'  📊 向量索引 ({VECTOR_INDEX_FILE}):')
            print(f'    - 向量数量: {results["index"]["count"]} 个')
            print(f'    - 向量维度: {results["index"]["dimension"]} 维')
            print(f'    - 文件大小: {results["index"]["size_kb"]:.1f}KB')
        else:
            print(f'  📊 向量索引: 文件不存在')
        
        if results['mapping']['count'] > 0:
            print(f'  🗂️ 映射文件 ({VECTOR_MAPPING_FILE}):')
            print(f'    - 映射数量: {results["mapping"]["count"]} 个')
            print(f'    - 文件大小: {results["mapping"]["size_kb"]:.1f}KB')
            print(f'    - 格式类型: {results["mapping"]["format"]}')
        else:
            print(f'  🗂️ 映射文件: 文件不存在')
        
        return {'status': 'success', **results}
        
    except Exception as e:
        print(f'❌ Faiss统计失败: {e}')
        return {'status': 'error', 'error': str(e)}

def check_neo4j_data():
    """检查Neo4j图数据"""
    try:
        # 检查Neo4j库是否可用
        if not NEO4J_AVAILABLE:
            print(f'❌ Neo4j库未安装，请运行: pip install neo4j')
            return {'status': 'error', 'error': 'Neo4j库未安装'}
        
        # 验证配置
        neo4j_user = NEO4J_CONFIG.get('user') or NEO4J_CONFIG.get('username')
        neo4j_password = NEO4J_CONFIG.get('password')
        neo4j_uri = NEO4J_CONFIG.get('uri')
        
        if not all([neo4j_uri, neo4j_user, neo4j_password]):
            print(f'❌ Neo4j配置不完整: uri={bool(neo4j_uri)}, user={bool(neo4j_user)}, password={bool(neo4j_password)}')
            return {'status': 'error', 'error': 'Neo4j配置缺失'}
        
        # 连接数据库
        try:
            driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
            driver.verify_connectivity()
        except Exception as conn_error:
            print(f'❌ Neo4j连接失败: {conn_error}')
            return {'status': 'error', 'error': f'连接失败: {conn_error}'}
        
        with driver.session() as session:
            # 节点统计
            result = session.run('MATCH (n) RETURN COUNT(n) as count')
            nodes_count = result.single()['count']
            
            # 关系统计
            result = session.run('MATCH ()-[r]->() RETURN COUNT(r) as count')
            relations_count = result.single()['count']
            
            # 节点类型统计
            result = session.run('MATCH (n) RETURN DISTINCT labels(n) as labels, COUNT(n) as count')
            node_types = {}
            for record in result:
                labels = record['labels']
                if labels:
                    label = labels[0] if labels else 'Unknown'
                    node_types[label] = record['count']
            
            # 关系类型统计
            result = session.run('MATCH ()-[r]->() RETURN type(r) as rel_type, COUNT(r) as count')
            relation_types = {}
            for record in result:
                rel_type = record['rel_type']
                relation_types[rel_type] = record['count']
            
            print(f'🔵 Neo4j图数据库统计:')
            print(f'  🔗 连接状态: ✅ 正常 ({neo4j_uri})')
            print(f'  📊 节点数量: {nodes_count} 个')
            if node_types:
                print(f'    - 类型分布: {dict(list(node_types.items())[:5])}{"..." if len(node_types) > 5 else ""}')
            
            print(f'  ➡️ 关系数量: {relations_count} 个')
            if relation_types:
                print(f'    - 类型分布: {dict(list(relation_types.items())[:5])}{"..." if len(relation_types) > 5 else ""}')
        
        driver.close()
        return {
            'status': 'success',
            'nodes': nodes_count,
            'relations': relations_count,
            'node_types': node_types,
            'relation_types': relation_types
        }
        
    except Exception as e:
        print(f'❌ Neo4j统计失败: {e}')
        return {'status': 'error', 'error': str(e)}

def check_filesystem_data():
    """检查文件系统技能数据"""
    try:
        if not os.path.exists(SKILLS_DIR):
            print(f'🟠 技能文件系统: 目录 {SKILLS_DIR} 不存在')
            return {'status': 'error', 'error': 'Skills directory not found'}
        
        # 扫描技能文件
        all_files = os.listdir(SKILLS_DIR)
        skill_files = [f for f in all_files if f.endswith('.py') and not f.startswith('__')]
        
        # 按类别统计
        categories = {}
        for skill_file in skill_files:
            if '_' in skill_file:
                category = skill_file.split('_')[0]
                categories[category] = categories.get(category, 0) + 1
        
        # 计算总大小
        total_size = 0
        for skill_file in skill_files:
            file_path = os.path.join(SKILLS_DIR, skill_file)
            total_size += os.path.getsize(file_path)
        
        size_kb = total_size / 1024
        
        print(f'🟠 技能文件系统统计 ({SKILLS_DIR}/):')
        print(f'  📁 总文件数: {len(all_files)} 个')
        print(f'  🐍 技能文件: {len(skill_files)} 个')
        print(f'  💾 总大小: {size_kb:.1f}KB')
        if categories:
            print(f'  📂 类别分布: {dict(list(categories.items())[:5])}{"..." if len(categories) > 5 else ""}')
        
        return {
            'status': 'success',
            'total_files': len(all_files),
            'skill_files': len(skill_files),
            'categories': categories,
            'size_kb': size_kb
        }
        
    except Exception as e:
        print(f'❌ 文件系统统计失败: {e}')
        return {'status': 'error', 'error': str(e)}

def print_summary(stats):
    """打印统计汇总"""
    print("\n" + "=" * 60)
    print("📈 数据汇总报告")
    print("=" * 60)
    
    total_records = 0
    total_size_mb = 0
    
    # 统计总记录数
    if stats['redis']['status'] == 'success':
        total_records += stats['redis'].get('stm_messages', 0)
        total_records += stats['redis'].get('wm_tasks', 0)
    
    if stats['sqlite']['status'] == 'success':
        total_records += stats['sqlite'].get('old_preferences', {}).get('count', 0)
        total_records += stats['sqlite'].get('new_preferences', {}).get('count', 0)
        total_records += stats['sqlite'].get('vector_metadata', {}).get('count', 0)
        total_size_mb += stats['sqlite'].get('file_size_mb', 0)
    
    if stats['faiss']['status'] == 'success':
        total_records += stats['faiss'].get('index', {}).get('count', 0)
        total_size_mb += stats['faiss'].get('index', {}).get('size_kb', 0) / 1024
        total_size_mb += stats['faiss'].get('mapping', {}).get('size_kb', 0) / 1024
    
    if stats['neo4j']['status'] == 'success':
        total_records += stats['neo4j'].get('nodes', 0)
        total_records += stats['neo4j'].get('relations', 0)
    
    if stats['filesystem']['status'] == 'success':
        total_records += stats['filesystem'].get('skill_files', 0)
        total_size_mb += stats['filesystem'].get('size_kb', 0) / 1024
    
    print(f"📊 总数据量: ~{total_records:,} 条记录")
    print(f"💾 总存储量: ~{total_size_mb:.2f}MB (不含Redis和Neo4j)")
    
    # 各系统状态
    print(f"\n🔍 系统状态:")
    systems = ['redis', 'sqlite', 'faiss', 'neo4j', 'filesystem']
    system_names = ['Redis', 'SQLite', 'Faiss', 'Neo4j', '文件系统']
    
    for system, name in zip(systems, system_names):
        status = stats[system]['status']
        if status == 'success':
            print(f"  ✅ {name}: 正常运行")
        else:
            print(f"  ❌ {name}: {stats[system].get('error', '未知错误')}")
    
    print("\n" + "="*60)
    print(f"✨ 统计完成! 系统数据丰富度: {'🌟🌟🌟' if total_records > 1000 else '🌟🌟' if total_records > 500 else '🌟'}")

def main():
    """主函数"""
    print_header()
    
    # 收集所有统计数据
    stats = {
        'redis': check_redis_data(),
        'sqlite': check_sqlite_data(),
        'faiss': check_faiss_data(),
        'neo4j': check_neo4j_data(),
        'filesystem': check_filesystem_data()
    }
    
    # 打印汇总
    print_summary(stats)
    
    return stats

if __name__ == "__main__":
    import sys
    
    # 检查命令行参数
    if len(sys.argv) > 1 and sys.argv[1] == '--health':
        # 快速健康检查模式
        print("🏥 快速健康检查模式")
        print("="*40)
        
        all_healthy = True
        
        # Redis
        try:
            redis_client = redis.Redis(**REDIS_CONFIG, decode_responses=True)
            redis_client.ping()
            print("✅ Redis: 正常")
        except Exception as e:
            print(f"❌ Redis: 失败 ({e})")
            all_healthy = False
        
        # SQLite
        try:
            if os.path.exists(SQLITE_DB):
                conn = sqlite3.connect(SQLITE_DB)
                conn.execute("SELECT 1")
                conn.close()
                print("✅ SQLite: 正常")
            else:
                print("⚠️ SQLite: 数据库文件不存在")
                all_healthy = False
        except Exception as e:
            print(f"❌ SQLite: 失败 ({e})")
            all_healthy = False
        
        # Faiss
        try:
            if os.path.exists(VECTOR_INDEX_FILE):
                index = faiss.read_index(VECTOR_INDEX_FILE)
                print(f"✅ Faiss: 正常 ({index.ntotal} 向量)")
            else:
                print("⚠️ Faiss: 向量文件不存在")
                all_healthy = False
        except Exception as e:
            print(f"❌ Faiss: 失败 ({e})")
            all_healthy = False
        
        # Neo4j
        if NEO4J_AVAILABLE:
            try:
                neo4j_user = NEO4J_CONFIG.get('user') or NEO4J_CONFIG.get('username')
                neo4j_password = NEO4J_CONFIG.get('password')
                neo4j_uri = NEO4J_CONFIG.get('uri')
                
                if all([neo4j_uri, neo4j_user, neo4j_password]):
                    driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
                    driver.verify_connectivity()
                    driver.close()
                    print("✅ Neo4j: 正常")
                else:
                    print("⚠️ Neo4j: 配置缺失")
                    all_healthy = False
            except Exception as e:
                print(f"❌ Neo4j: 失败 ({e})")
                all_healthy = False
        else:
            print("⚠️ Neo4j: 库未安装")
        
        print("="*40)
        if all_healthy:
            print("🌟 所有核心组件正常运行!")
            sys.exit(0)
        else:
            print("⚠️ 部分组件存在问题")
            sys.exit(1)
    
    # 正常详细统计模式
    try:
        stats = main()
    except KeyboardInterrupt:
        print("\n\n⚠️ 统计中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ 统计过程中发生错误: {e}")
        sys.exit(1)
