# -*- coding: utf-8 -*-


import os
import redis
import numpy as np
import faiss
import json
import sqlite3
from neo4j import GraphDatabase
import uuid
import time
from typing import List, Dict, Any, Optional
import requests
from contextlib import asynccontextmanager # [新增] 导入 asynccontextmanager

# --- FastAPI & Pydantic ---
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# --- 0. 辅助工具 ---
class EnhancedJSONEncoder(json.JSONEncoder):
    """一个可以处理Numpy数据类型的JSON编码器"""
    def default(self, o):
        if isinstance(o, np.integer): return int(o)
        if isinstance(o, np.floating): return float(o)
        if isinstance(o, np.ndarray): return o.tolist()
        return super(EnhancedJSONEncoder, self).default(o)

# --- 1. 短期记忆模块 (STM) - 优化版：存储对话摘要 ---
class ShortTermMemory:
    def __init__(self, redis_client, conversation_ttl=1800):
        self.client = redis_client
        self.ttl = conversation_ttl
        print("✅ 短期记忆模块 (Redis Hash结构) 初始化完成。")
    
    def store_summary(self, conversation_id: str, conversation_summary: Dict[str, Any], round_id: int):
        """存储对话摘要（新方法）- 接受字典格式的摘要数据"""
        # 从传入的摘要数据中提取信息
        summary_data = {
            "round_id": round_id,
            "user_request": conversation_summary.get('user_request', ''),
            "final_answer": conversation_summary.get('final_answer', ''),
            "memories_used": conversation_summary.get('memories_used', []),
            "timestamp": conversation_summary.get('timestamp', time.time()),
            "conversation_length": conversation_summary.get('conversation_length', 0)
        }
        
        # 使用Hash结构存储，字段名为轮次号
        key = f"stm:conversation:{conversation_id}:summaries"
        self.client.hset(key, f"round_{round_id}", json.dumps(summary_data, cls=EnhancedJSONEncoder))
        self.client.expire(key, self.ttl)
        print(f"🧠 STM: 存储第{round_id}轮对话摘要到 {conversation_id}")
    
    def retrieve_summaries(self, conversation_id: str, last_k: int = 15) -> List[Dict[str, Any]]:
        """检索对话摘要（新方法）"""
        key = f"stm:conversation:{conversation_id}:summaries"
        all_summaries = self.client.hgetall(key)
        
        if not all_summaries:
            print(f"🧠 STM: 对话 {conversation_id} 无摘要记录。")
            return []
        
        # 解析并按轮次排序
        summaries = []
        for field, data in all_summaries.items():
            try:
                summary = json.loads(data)
                summaries.append(summary)
            except json.JSONDecodeError as e:
                print(f"⚠️ STM: 解析摘要数据失败: {e}")
                continue
        
        # 按轮次号排序，返回最近的K条
        summaries.sort(key=lambda x: x.get('round_id', x.get('round', 0)))
        result = summaries[-last_k:] if len(summaries) > last_k else summaries
        print(f"🧠 STM: 从对话 {conversation_id} 中检索到 {len(result)} 条摘要。")
        return result
    
    # 保留原有方法以兼容旧代码
    def store(self, conversation_id: str, message: Dict[str, Any]):
        """存储原始消息（兼容方法）"""
        key = f"stm:conversation:{conversation_id}"
        self.client.rpush(key, json.dumps(message, cls=EnhancedJSONEncoder))
        self.client.expire(key, self.ttl)
        print(f"🧠 STM: 存储消息到对话 {conversation_id}")
    
    def retrieve(self, conversation_id: str, last_k: int = 10) -> List[Dict[str, Any]]:
        """检索原始消息（兼容方法）"""
        key = f"stm:conversation:{conversation_id}"
        
        # 检查key的类型 - 修复decode错误
        try:
            key_type_bytes = self.client.type(key)
            if key_type_bytes:
                key_type = key_type_bytes.decode('utf-8') if isinstance(key_type_bytes, bytes) else str(key_type_bytes)
            else:
                key_type = 'none'
        except Exception as e:
            print(f"⚠️ STM: 检查key类型失败: {e}")
            key_type = 'none'
        
        if key_type == 'string':
            # 新格式：JSON对象存储
            data = self.client.get(key)
            if data:
                conv_data = json.loads(data)
                messages = conv_data.get('messages', [])
                print(f"🧠 STM: 从对话 {conversation_id} 中检索到 {len(messages)} 条消息。")
                return messages[-last_k:] if messages else []
        elif key_type == 'list':
            # 旧格式：list存储（当前使用的格式）
            items = self.client.lrange(key, -last_k, -1)
            print(f"🧠 STM: 从对话 {conversation_id} 中检索最近 {len(items)} 条消息。")
            return [json.loads(item.decode('utf-8') if isinstance(item, bytes) else item) for item in items]
        
        print(f"🧠 STM: 对话 {conversation_id} 无记录。")
        return []
    def clear(self, conversation_id: str):
        key = f"stm:conversation:{conversation_id}"; self.client.delete(key)
        print(f"🗑️ STM: 清除对话 {conversation_id} 的短期记忆。")
class WorkingMemory:
    def __init__(self, redis_client):
        self.client = redis_client
        print("✅ 工作记忆模块 (Redis) 初始化完成。")
    def store(self, agent_id: str, task_id: str, data: Dict[str, Any]):
        key = f"wm:task:{task_id}"; self.client.set(key, json.dumps(data, cls=EnhancedJSONEncoder))
        print(f"📝 WM: 为任务 {task_id} 更新工作记忆。")
    def retrieve(self, agent_id: str = None, task_id: str = None) -> Optional[Dict[str, Any]]:
        # 支持多种查询方式
        if task_id and not agent_id:
            # 直接通过task_id查询
            key = f"wm:task:{task_id}"
            data = self.client.get(key)
            if data:
                print(f"📝 WM: 检索到任务 {task_id} 的工作记忆。")
                return json.loads(data)
        
        if agent_id and task_id:
            # 通过agent_id和task_id查询
            key = f"wm:task:{task_id}"
            data = self.client.get(key)
            if data:
                print(f"📝 WM: 检索到任务 {task_id} 的工作记忆。")
                return json.loads(data)
        
        print(f"📝 WM: 未找到任务 {task_id} 的工作记忆。")
        return None
    def clear(self, agent_id: str, task_id: str):
        key = f"wm:task:{task_id}"; self.client.delete(key)
        print(f"🗑️ WM: 清除任务 {task_id} 的工作记忆。")
class StructuredLTM:
    def __init__(self, db_path='ltm.db'):
        self.conn = sqlite3.connect(db_path, check_same_thread=False); self.cursor = self.conn.cursor()
        self.cursor.execute("CREATE TABLE IF NOT EXISTS preferences (user_id TEXT, key TEXT, value TEXT, updated_at REAL, PRIMARY KEY (user_id, key))")
        self.conn.commit(); print(f"✅ 结构化长期记忆模块 (SQLite @ {db_path}) 初始化完成。")
    def store(self, user_id: str, key: str, value: Any):
        # 添加数据库锁定重试机制
        max_retries = 5
        for retry in range(max_retries):
            try:
                self.cursor.execute("INSERT OR REPLACE INTO preferences VALUES (?, ?, ?, ?)", (user_id, key, json.dumps(value), time.time()))
                self.conn.commit()
                break
            except sqlite3.OperationalError as e:
                if "database is locked" in str(e) and retry < max_retries - 1:
                    import time as time_module
                    time_module.sleep(0.1 * (retry + 1))  # 递增等待时间
                    continue
                else:
                    raise
        print(f"⚙️ LTM: 为用户 {user_id} 存储偏好 '{key}'。")
    def retrieve(self, user_id: str, key: str) -> Optional[Any]:
        # 先尝试ltm_preferences表
        self.cursor.execute("SELECT value FROM ltm_preferences WHERE user_id = ? AND key = ?", (user_id, key))
        row = self.cursor.fetchone()
        if row:
            print(f"⚙️ LTM: 检索到用户 {user_id} 的偏好 '{key}'。")
            # 数据库中存储的是字符串，直接返回，不需要json.loads
            return row[0]
        
        # 兼容旧表名
        self.cursor.execute("SELECT value FROM preferences WHERE user_id = ? AND key = ?", (user_id, key))
        row = self.cursor.fetchone()
        if row:
            print(f"⚙️ LTM: 检索到用户 {user_id} 的偏好 '{key}'。")
            return json.loads(row[0])
        
        print(f"⚙️ LTM: 未找到用户 {user_id} 的偏好 '{key}'。")
        return None
class KnowledgeGraphMemory:
    def __init__(self, uri="bolt://localhost:7687", user="neo4j", password="*****"):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        print(f"✅ 知识图谱模块 (Neo4j @ {uri}) 初始化完成。默认用户: {user}")

    def store(self, subject: str, relation: str, obj: str):
        with self.driver.session() as session:
            session.run(
                "MERGE (a:Entity {name: $subject}) "
                "MERGE (b:Entity {name: $object}) "
                "MERGE (a)-[r:RELATION {type: $relation}]->(b)",
                subject=subject, relation=relation, object=obj
            )
        print(f"🕸️ KG: 存储关系 '{subject} -[{relation}]-> {obj}'。")

    def retrieve(self, subject: str, relation: str) -> dict:
        with self.driver.session() as session:
            # 策略1: 精确匹配
            result = session.run(
                "MATCH (a)-[r:RELATION]->(b) WHERE a.name = $subject RETURN a.name as subject, type(r) as relation, b.name as target",
                subject=subject
            )
            records = result.data()
            
            # 策略2: 如果精确匹配失败，尝试模糊匹配
            if not records:
                # 提取关键词进行模糊查询
                keywords = subject.split()
                for keyword in keywords:
                    if len(keyword) > 1:  # 跳过太短的词
                        result = session.run(
                            "MATCH (a)-[r:RELATION]->(b) WHERE a.name CONTAINS $keyword RETURN a.name as subject, type(r) as relation, b.name as target LIMIT 3",
                            keyword=keyword
                        )
                        records = result.data()
                        if records:
                            print(f"🕸️ KG: 通过关键词 '{keyword}' 找到相关关系")
                            break
            
            if records:
                # 格式化返回结果
                results = []
                for record in records:
                    results.append({
                        'subject': record['subject'],
                        'relation': record['relation'], 
                        'target': record['target']
                    })
                print(f"🕸️ KG: 查询 '{subject}' 找到 {len(results)} 条关系")
                return {'status': 'success', 'data': results}
            else:
                print(f"🕸️ KG: 未查询到 '{subject}' 相关的任何关系。")
                return {'status': 'success', 'data': None}
class ProceduralMemory:
    def __init__(self, skills_dir='skills'):
        self.skills_dir = skills_dir;
        if not os.path.exists(self.skills_dir): os.makedirs(self.skills_dir)
        print(f"✅ 程序性记忆模块 (File System @ {skills_dir}) 初始化完成。")
    def store(self, skill_name: str, code: str):
        with open(os.path.join(self.skills_dir, f"{skill_name}.py"), "w", encoding="utf-8") as f: f.write(code)
        print(f"🛠️ ProcMem: 存储新技能 '{skill_name}'。")
    def retrieve(self, skill_name: str, *args, **kwargs) -> Any:
        try:
            module_path = f"{self.skills_dir}.{skill_name}"; skill_module = __import__(module_path, fromlist=[None])
            result = skill_module.execute(*args, **kwargs); print(f"🚀 ProcMem: 成功执行技能 '{skill_name}'。"); return result
        except (ImportError, AttributeError) as e: print(f"❌ ProcMem: 执行技能 '{skill_name}' 失败: {e}"); return None

# --- 3. 向量记忆 (Vector Memory) ---
class VectorMemory:
    def __init__(self, embedding_service_url: str, embedding_model_name: str, dimension: int, db_path='ltm.db'):
        self.embedding_service_url = embedding_service_url
        self.embedding_model_name = embedding_model_name
        self.dimension = dimension
        self._needs_save = False  # 🆕 保存标志
        
        # 加载现有索引或创建新索引
        index_path = 'vector_index.faiss'
        mapping_path = 'vector_mapping.json'
        
        if os.path.exists(index_path):
            self.index = faiss.read_index(index_path)
            print(f"📁 加载现有向量索引: {self.index.ntotal} 个向量")
        else:
            self.index = faiss.IndexFlatL2(self.dimension)
            print(f"🆕 创建新向量索引")
        
        # 加载向量映射
        if os.path.exists(mapping_path):
            with open(mapping_path, 'r') as f:
                mapping_data = json.load(f)
                # 处理旧格式：{"0": "0", "1": "1", ...}
                self.vector_mapping = {int(k): v for k, v in mapping_data.items()}
            print(f"📁 加载向量映射: {len(self.vector_mapping)} 个映射")
        else:
            self.vector_mapping = {}
            print(f"🆕 创建新向量映射")
        
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS vector_metadata (
                vector_id INTEGER PRIMARY KEY,
                memory_type TEXT,
                text TEXT,
                metadata TEXT
            )
        """)
        self.conn.commit()
        print(f"✅ 向量记忆模块 (Faiss + 外部嵌入服务 @ {embedding_service_url}) 初始化完成。")
        print(f"   - 使用模型: {self.embedding_model_name}")
        print(f"   - 向量维度: {self.dimension}")

    def _get_embedding(self, text: str) -> np.ndarray:
        try:
            payload = {"model": self.embedding_model_name, "input": [text]}
            response = requests.post(self.embedding_service_url, json=payload, timeout=10)
            response.raise_for_status()
            result = response.json()
            embedding = np.array(result['data'][0]['embedding'], dtype='float32')
            return embedding
        except requests.exceptions.RequestException as e:
            print(f"❌ 调用嵌入服务失败: {e}"); raise
        except (KeyError, IndexError) as e:
            print(f"❌ 解析嵌入服务响应失败: {e}"); raise

    def store(self, memory_type: str, text: str, metadata: Dict[str, Any]):
        embedding = self._get_embedding(text)
        
        # 生成唯一的vector_id，使用时间戳+随机数确保唯一性
        import time
        import random
        vector_id = int(time.time() * 1000000) + random.randint(1000, 9999)
        
        # 检查ID是否已存在，如果存在则重新生成
        max_retries = 10
        for retry in range(max_retries):
            self.cursor.execute("SELECT COUNT(*) FROM vector_metadata WHERE vector_id = ?", (vector_id,))
            if self.cursor.fetchone()[0] == 0:
                break
            vector_id = int(time.time() * 1000000) + random.randint(1000, 9999)
            if retry == max_retries - 1:
                print(f"❌ 无法生成唯一vector_id，重试{max_retries}次后失败")
                return
        
        # 记录当前index位置和vector_id的映射
        current_index_pos = self.index.ntotal
        self.vector_mapping[current_index_pos] = vector_id
        
        # 添加向量到索引
        self.index.add(np.array([embedding]))
        
        # 准备元数据
        metadata['memory_type'] = memory_type
        metadata['text'] = text
        
        # 存储到数据库，添加重试机制处理数据库锁定
        max_db_retries = 5
        for db_retry in range(max_db_retries):
            try:
                self.cursor.execute(
                    "INSERT INTO vector_metadata (vector_id, memory_type, content, metadata) VALUES (?, ?, ?, ?)",
                    (vector_id, memory_type, text, json.dumps(metadata, cls=EnhancedJSONEncoder))
                )
                self.conn.commit()
                break
            except sqlite3.OperationalError as e:
                if "database is locked" in str(e) and db_retry < max_db_retries - 1:
                    import time as time_module
                    time_module.sleep(0.1 * (db_retry + 1))  # 递增等待时间
                    continue
                else:
                    raise
            except sqlite3.IntegrityError as e:
                if "UNIQUE constraint failed" in str(e):
                    # ID冲突，重新生成
                    vector_id = int(time.time() * 1000000) + random.randint(1000, 9999)
                    self.vector_mapping[current_index_pos] = vector_id
                    if db_retry < max_db_retries - 1:
                        continue
                raise
        
        print(f"💾 VectorDB ({memory_type}): 存储向量ID {vector_id} - '{text[:30]}...'")
        
        # 🆕 标记需要保存，但不立即保存（避免频繁I/O）
        self._needs_save = True

    def _save_index_and_mapping(self):
        """保存向量索引和映射关系到磁盘"""
        if not self._needs_save:
            return
            
        try:
            # 保存向量索引
            faiss.write_index(self.index, 'vector_index.faiss')
            
            # 保存向量映射
            with open('vector_mapping.json', 'w', encoding='utf-8') as f:
                json.dump(self.vector_mapping, f, ensure_ascii=False, indent=2)
            
            print(f"📁 向量索引和映射已保存 (索引大小: {self.index.ntotal})")
            self._needs_save = False
        except Exception as e:
            print(f"⚠️  保存索引失败: {e}")
    
    def save_if_needed(self):
        """如果有更改则保存索引和映射"""
        self._save_index_and_mapping()

    def retrieve(self, query_text: str, k: int = 5, filter_by_type: Optional[str] = None) -> List[Dict[str, Any]]:
        query_embedding = self._get_embedding(query_text)
        distances, indices = self.index.search(np.array([query_embedding]), k * 2)
        results = []
        for i, idx in enumerate(indices[0]):
            if len(results) >= k:
                break
            # 使用映射获取正确的vector_id
            if idx in self.vector_mapping:
                vector_id = self.vector_mapping[idx]
                self.cursor.execute("SELECT metadata, memory_type FROM vector_metadata WHERE vector_id = ?", (vector_id,))
                row = self.cursor.fetchone()
                if row:
                    metadata = json.loads(row[0])
                    memory_type = row[1]
                    if filter_by_type and memory_type != filter_by_type:
                        continue
                    results.append({'metadata': metadata, 'score': float(distances[0][i])})
        print(f"🔍 VectorDB: 查询 '{query_text[:30]}...'，找到 {len(results)} 个结果。")
        return results

# --- 7. 记忆编排器 (Memory Orchestrator) ---
class MemoryOrchestrator:
    def __init__(self):
        print("\n--- 初始化记忆编排器 ---")
        self.redis_client = redis.Redis(decode_responses=True)
        try:
            self.redis_client.ping()
            print("🔗 Redis 连接成功。")
        except redis.exceptions.ConnectionError as e:
            print(f"❌ Redis 连接失败: {e}\n请确保Redis服务器正在运行。"); exit(1)
        db_path = 'ltm.db'
        self.vector_mem = VectorMemory(
            embedding_service_url="http://127.0.0.1:7999/v1/embeddings",
            embedding_model_name="qwen3-embedding-0.6b",
            dimension=1024,
            db_path=db_path
        )
        self.stm = ShortTermMemory(self.redis_client)
        self.wm = WorkingMemory(self.redis_client)
        self.structured_ltm = StructuredLTM(db_path=db_path)
        self.kg_mem = KnowledgeGraphMemory()
        self.procedural_mem = ProceduralMemory()
        print("--- 记忆编排器初始化完成 ---\n")

    def store(self, memory_type: str, **kwargs):
        if memory_type == 'stm': 
            # 支持新版摘要存储和旧版消息存储
            if 'conversation_summary' in kwargs:
                # 新版摘要存储
                self.stm.store_summary(
                    kwargs['conversation_id'], 
                    kwargs['conversation_summary'],
                    kwargs['round_id']
                )
            else:
                # 旧版消息存储，保持向后兼容
                message = {
                    'role': kwargs.get('role', 'user'),
                    'content': kwargs.get('content', ''),
                    'timestamp': kwargs.get('timestamp', time.time())
                }
                self.stm.store(kwargs['conversation_id'], message)
        elif memory_type == 'wm': 
            # context重命名为data
            data = kwargs.get('context', kwargs.get('data', {}))
            self.wm.store(kwargs['agent_id'], kwargs['task_id'], data)
        elif memory_type in ['episodic', 'semantic_fact', 'ltm_doc']:
            vec_type_map = {'semantic_fact': 'semantic', 'ltm_doc': 'ltm_doc', 'episodic': 'episodic'}
            self.vector_mem.store(vec_type_map[memory_type], kwargs['text'], kwargs['metadata'])
        elif memory_type == 'episodic': 
            # 情节记忆存储
            vector_id = self.store_vector(kwargs['text'], kwargs.get('metadata', {}), 'episodic')
            return {'status': 'success', 'vector_id': vector_id}
        elif memory_type == 'semantic_fact': 
            # 语义事实存储
            vector_id = self.store_vector(kwargs['text'], kwargs.get('metadata', {}), 'semantic')
            return {'status': 'success', 'vector_id': vector_id}
        elif memory_type == 'ltm_preference': self.structured_ltm.store(kwargs['user_id'], kwargs['key'], kwargs['value'])
        elif memory_type == 'kg_relation': self.kg_mem.store(kwargs['subject'], kwargs['relation'], kwargs['obj'])
        elif memory_type == 'procedural_skill': self.procedural_mem.store(kwargs['skill_name'], kwargs['code'])
        else: raise HTTPException(status_code=400, detail=f"未知的记忆类型: {memory_type}")
    def retrieve(self, memory_type: str, **kwargs) -> Any:
        if memory_type == 'stm': 
            # 支持旧版消息检索和新版摘要检索
            if 'retrieve_type' in kwargs and kwargs['retrieve_type'] == 'summaries':
                return self.stm.retrieve_summaries(kwargs['conversation_id'], kwargs.get('last_k', 15))
            else:
                return self.stm.retrieve(kwargs['conversation_id'], kwargs.get('last_k', 10))
        elif memory_type == 'wm': 
            # 支持只传task_id或同时传agent_id和task_id
            agent_id = kwargs.get('agent_id')
            task_id = kwargs.get('task_id')
            return self.wm.retrieve(agent_id, task_id)
        elif memory_type in ['episodic', 'semantic', 'semantic_fact', 'ltm_doc']:
            vec_type_map = {'semantic_fact': 'semantic', 'semantic': 'semantic', 'ltm_doc': 'ltm_doc', 'episodic': 'episodic'}
            return self.vector_mem.retrieve(kwargs['query_text'], kwargs.get('k', 5), vec_type_map.get(memory_type))
        elif memory_type == 'episodic': 
            # 情节记忆检索
            results = self.retrieve_vector(kwargs['query_text'], memory_type='episodic')
            return {'status': 'success', 'data': results}
        elif memory_type == 'semantic_fact': 
            # 语义事实检索
            results = self.retrieve_vector(kwargs['query_text'], memory_type='semantic')
            return {'status': 'success', 'data': results}
        elif memory_type == 'ltm_preference': return self.structured_ltm.retrieve(kwargs['user_id'], kwargs['key'])
        elif memory_type == 'kg_relation': 
            # 知识图谱查询已经返回标准格式，直接返回
            return self.kg_mem.retrieve(kwargs['subject'], kwargs['relation'])
        elif memory_type == 'procedural_skill': return self.procedural_mem.retrieve(kwargs['skill_name'], *kwargs.get('args', []), **kwargs.get('kwargs', {}))
        else: raise HTTPException(status_code=400, detail=f"未知的记忆类型: {memory_type}")
    def clear(self, memory_type: str, **kwargs):
        if memory_type == 'stm': self.stm.clear(kwargs['conversation_id'])
        elif memory_type == 'wm': self.wm.clear(kwargs['agent_id'], kwargs['task_id'])
        else: raise HTTPException(status_code=400, detail=f"清除操作不支持记忆类型: {memory_type}")

# --- 8. FastAPI 应用 [已修正] ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    使用 lifespan 事件处理器来管理应用的启动和关闭事件。
    """
    # 应用启动时执行的代码
    print("🚀 记忆服务启动完成，等待客户端植入知识...")
    yield
    # 应用关闭时执行的代码
    print("👋 记忆服务正在关闭。")

app = FastAPI(title="Agent Memory System API", version="1.4", lifespan=lifespan)
orchestrator = MemoryOrchestrator()

@app.get("/health")
def health_check():
    """健康检查端点"""
    return {"status": "healthy", "message": "Memory service is running"}

class StoreRequest(BaseModel): memory_type: str; params: Dict[str, Any]
class RetrieveRequest(BaseModel): memory_type: str; params: Dict[str, Any]
class ClearRequest(BaseModel): memory_type: str; params: Dict[str, Any]
@app.post("/store")
def store_memory(request: StoreRequest):
    try: 
        orchestrator.store(request.memory_type, **request.params)
        # 🆕 存储后保存向量索引（如果有更改）
        orchestrator.vector_mem.save_if_needed()
        return {"status": "success"}
    except Exception as e: 
        print(f"❌ API存储错误 - 记忆类型: {request.memory_type}, 参数: {request.params}, 错误: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
@app.post("/retrieve")
def retrieve_memory(request: RetrieveRequest):
    try: 
        result = orchestrator.retrieve(request.memory_type, **request.params)
        # 🔧 修复双层嵌套：如果result已经是标准格式，直接返回
        if isinstance(result, dict) and 'status' in result:
            return result
        else:
            return {"status": "success", "data": result}
    except Exception as e: 
        print(f"❌ API错误 - 记忆类型: {request.memory_type}, 参数: {request.params}, 错误: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
@app.post("/clear")
def clear_memory(request: ClearRequest):
    try: orchestrator.clear(request.memory_type, **request.params); return {"status": "success"}
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

# 原有的 @app.on_event("startup") 已被移除

