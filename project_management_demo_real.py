# -*- coding: utf-8 -*-
import os
import requests
import json
import uuid
import time
import re
import logging
import importlib.util
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv
from conversation_value_filter import ConversationValueFilter, ConversationItem, FilterResult
from task_todo_manager import TaskTodoManager

# --- 日志配置 ---
def setup_logging():
    """配置日志记录，输出到外部文件"""
    logger = logging.getLogger()
    logger.setLevel(logging.INFO) 
    fh = logging.FileHandler('project_management_demo.log', mode='w', encoding='utf-8', errors='replace')
    fh.setLevel(logging.INFO)
    debug_fh = logging.FileHandler('project_management_demo_debug.log', mode='w', encoding='utf-8', errors='replace')
    debug_fh.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - [%(module)s:%(funcName)s:%(lineno)d] - %(message)s'
    )
    fh.setFormatter(formatter)
    debug_fh.setFormatter(formatter)
    logger.addHandler(fh)
    logger.addHandler(debug_fh)

logger = logging.getLogger(__name__)

# --- 配置 ---
load_dotenv()

# 全局常量
MEMORY_SERVICE_URL = "http://127.0.0.1:8000"
USER_ID = "project_manager_alice"
AGENT_ID = "agent_project_management_assistant"
SKILLS_DIR = 'skills'

# --- OpenAI 客户端初始化 ---
try:
    api_key = os.getenv("AZURE_OPENAI_API_KEY")
    base_url = os.getenv("AZURE_OPENAI_ENDPOINT")
    model_name = os.getenv("AZURE_OPENAI_DEPLOYMENT")
    if not all([api_key, base_url, model_name]): raise ValueError("❌ 错误: Azure OpenAI 配置不完整。")
    azure_client = OpenAI(
        api_key=api_key,
        base_url=base_url,
        default_query={"api-version": "preview"}, 
        timeout=60.0
    )
    logger.info("Azure OpenAI 客户端初始化成功 (使用 responses API)")
except Exception as e:
    logger.exception("OpenAI客户端初始化失败")
    print(f"❌ 关键服务初始化失败，请检查日志 project_management_demo.log。错误: {e}")
    exit(1)

# --- 辅助函数 ---
def call_memory_service(endpoint: str, payload: dict) -> dict:
    url = f"{MEMORY_SERVICE_URL}/{endpoint}"
    logger.debug(f"准备调用记忆服务: Endpoint={endpoint}, Payload={json.dumps(payload, ensure_ascii=False)}")
    try:
        response = requests.post(url, json=payload, timeout=15)
        response.raise_for_status()
        json_response = response.json()
        logger.debug(f"记忆服务响应: {json.dumps(json_response, ensure_ascii=False)}")
        return json_response
    except requests.exceptions.RequestException as e:
        error_message = f"调用记忆服务失败: {e}"
        logger.error(error_message)
        return {"status": "error", "detail": error_message}

class ProjectManagementAgent:
    def __init__(self, user_id, agent_id):
        self.user_id = user_id
        self.agent_id = agent_id
        self.conversation_history = []  # 当前轮次的推理对话
        self.conversation_id = str(uuid.uuid4())  # 为STM同步生成会话ID
        self.round_id = 0  # 对话轮次计数器
        
        logger.info(f"Agent {self.agent_id} 正在为用户 {self.user_id} 进行初始化...")
        logger.info(f"会话ID: {self.conversation_id}")
        
        # 初始化对话价值过滤器
        self.conversation_filter = ConversationValueFilter()
        logger.info("✅ 3级漏斗记忆过滤器初始化完成")
        
        # 初始化Todo追踪管理器
        self.todo_manager = TaskTodoManager()
        logger.info("✅ 任务Todo追踪管理器初始化完成")
        
        self.tools_definitions, self.tool_functions = self._initialize_tools()
        logger.info("项目管理Agent已准备就绪。")

    def _initialize_tools(self):
        """[项目管理版] 为七大记忆模块提供完整、精确的工具集"""
        tool_functions = {}
        tools_definitions = []

        # 1. 动态加载外部技能 (程序性记忆)
        if not os.path.exists(SKILLS_DIR): os.makedirs(SKILLS_DIR); logger.info(f"技能目录 '{SKILLS_DIR}' 不存在，已自动创建。")
        for filename in os.listdir(SKILLS_DIR):
            if filename.endswith('.py') and not filename.startswith('__'):
                skill_name = filename[:-3]
                
                # 过滤不符合OpenAI函数名规范的技能名（包含中文字符）
                if not re.match(r'^[a-zA-Z0-9_-]+$', skill_name):
                    logger.debug(f"跳过不符合函数名规范的技能: {skill_name}")
                    continue
                
                try:
                    module_path = f"{SKILLS_DIR}.{skill_name}"
                    spec = importlib.util.spec_from_file_location(module_path, os.path.join(SKILLS_DIR, filename))
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    if hasattr(module, 'get_skill_metadata'):
                        metadata = module.get_skill_metadata()
                        
                        # 兼容三种参数格式：列表、字典或完整的OpenAI schema
                        params = metadata.get("parameters", [])
                        if isinstance(params, list):
                            # 列表格式：['param1', 'param2']
                            params_schema = {
                                "type": "object",
                                "properties": {param: {"type": "string"} for param in params},
                                "required": params
                            }
                        elif isinstance(params, dict) and "type" in params:
                            # 完整的OpenAI schema格式
                            params_schema = params
                        else:
                            # 字典格式：{'param1': {'description': '...', 'required': True}}
                            params_schema = {
                                "type": "object", 
                                "properties": {k: {"type": "string", "description": v.get("description", "")} for k, v in params.items()}, 
                                "required": [k for k, v in params.items() if v.get("required")]
                            }
                        
                        tools_definitions.append({"type": "function", "name": skill_name, "description": metadata.get("description"), "parameters": params_schema})
                        tool_functions[skill_name] = (lambda s_name: lambda **kwargs: self._execute_skill(skill_name=s_name, kwargs=kwargs))(skill_name)
                        logger.info(f"成功动态加载[程序记忆]技能: {skill_name}")
                except Exception as e:
                    logger.error(f"加载技能 {skill_name} 失败: {e}")
        
        # 2. 加入与记忆模块一一对应的内置工具
        meta_tools_def = [
            {"type": "function", "name": "query_ltm_preference", "description": "查询用户的【长期偏好记忆】。当你需要了解用户的习惯、喜好（如管理风格、会议偏好等）时必须使用此工具。", "parameters": {"type": "object", "properties": {"key": {"type": "string", "description": "要查询的偏好键名，例如 'meeting_style' 或 'management_style'。"}}, "required": ["key"]}},
            {"type": "function", "name": "query_episodic_memory", "description": "查询【情节记忆】，回顾过去发生的具体事件或已完成的任务。例如回顾上次的项目里程碑会议或查找Sprint回顾会议记录。", "parameters": {"type": "object", "properties": {"query_text": {"type": "string", "description": "描述你要查找的事件或任务的关键词。"}}, "required": ["query_text"]}},
            {"type": "function", "name": "query_semantic_memory", "description": "查询【语义记忆】，查找客观事实、标准流程或项目管理知识。例如查询敏捷开发最佳实践或查找风险管理流程。", "parameters": {"type": "object", "properties": {"query_text": {"type": "string", "description": "描述你要查找的事实或知识的关键词。"}}, "required": ["query_text"]}},
            {"type": "function", "name": "query_knowledge_graph", "description": "查询【知识图谱】，探索实体之间的关系。例如查询Bob的技能和职责或查询团队协作关系。", "parameters": {"type": "object", "properties": {"subject": {"type": "string", "description": "关系的主体"}, "relation": {"type": "string", "description": "要查询的关系类型"}}, "required": ["subject", "relation"]}},
            {"type": "function", "name": "query_stm", "description": "查询【短期记忆STM】，获取当前对话会话中的历史消息和上下文信息。用于回顾最近的对话内容或查找会话相关的临时信息。", "parameters": {"type": "object", "properties": {"conversation_id": {"type": "string", "description": "对话会话ID，不填则使用当前会话"}, "limit": {"type": "integer", "description": "返回的记忆条数限制，默认10"}}, "required": []}},
            {"type": "function", "name": "manage_working_memory", "description": "管理【工作记忆】，用于跟踪一个需要多步骤完成的复杂任务。可以创建(create)、更新(update)、检索(retrieve)或清除(clear)一个任务。", "parameters": {"type": "object", "properties": {"action": {"type": "string", "description": "操作类型，可选 'create', 'update', 'retrieve', 'clear'"}, "task_id": {"type": "string", "description": "任务的唯一ID"}, "data": {"type": "object", "description": "在create或update时传入的任务数据"}}, "required": ["action", "task_id"]}},
            {"type": "function", "name": "consolidate_memory", "description": "当你成功为用户完成一项重要任务后，调用此工具将关键成果作为新的【情节记忆】存入长期记忆库。", "parameters": {"type": "object", "properties": {"summary": {"type": "string", "description": "对需要被记忆的核心成果的简洁概括。"}}, "required": ["summary"]}},
            # 项目管理专项技能
            {"type": "function", "name": "generate_gantt_chart", "description": "生成项目甘特图，展示任务时间安排和依赖关系。帮助项目经理可视化项目进度和资源分配。", "parameters": {"type": "object", "properties": {"project_name": {"type": "string", "description": "项目名称"}, "tasks": {"type": "array", "description": "任务列表，每个任务包含name、duration、dependencies", "items": {"type": "object", "properties": {"name": {"type": "string"}, "duration": {"type": "integer"}, "dependencies": {"type": "array", "items": {"type": "string"}}}}}, "start_date": {"type": "string", "description": "项目开始日期，格式YYYY-MM-DD"}}, "required": []}},
            {"type": "function", "name": "assess_project_risks", "description": "评估项目风险并生成风险管理报告。分析项目中的潜在风险并提供缓解策略。", "parameters": {"type": "object", "properties": {"project_type": {"type": "string", "description": "项目类型，如e-commerce"}, "team_size": {"type": "integer", "description": "团队规模（人数）"}, "budget": {"type": "integer", "description": "项目预算（万元）"}, "duration_months": {"type": "integer", "description": "项目周期（月）"}}, "required": []}},
            {"type": "function", "name": "end_conversation", "description": "当用户明确表示对话结束或任务已全部完成时调用。", "parameters": {"type": "object", "properties": {}}}
        ]
        tools_definitions.extend(meta_tools_def)
        tool_functions["query_ltm_preference"] = self._query_ltm_preference
        tool_functions["query_episodic_memory"] = self._query_episodic_memory
        tool_functions["query_semantic_memory"] = self._query_semantic_memory
        tool_functions["query_knowledge_graph"] = self._query_knowledge_graph
        tool_functions["query_stm"] = self._query_stm
        tool_functions["manage_working_memory"] = self._manage_working_memory
        tool_functions["consolidate_memory"] = self._consolidate_memory
        tool_functions["generate_gantt_chart"] = self._generate_gantt_chart
        tool_functions["assess_project_risks"] = self._assess_project_risks
        tool_functions["end_conversation"] = self._end_conversation
        
        logger.info(f"Agent工具集初始化完成，共加载 {len(tools_definitions)} 个工具。")
        return tools_definitions, tool_functions

    def _get_system_prompt(self):
        """项目管理助手的系统提示"""
        return f"""你是{self.agent_id}，一个专业的项目管理智能助手，为项目经理{self.user_id}提供全方位的项目管理支持。

**【你的专业领域】**
- 📋 项目规划与进度管理
- 👥 团队协调与资源分配  
- 📊 风险识别与质量控制
- 💡 最佳实践建议与决策支持
- 📈 数据分析与报告生成

**【当前项目背景】**
你正在协助管理一个"电商平台重构项目"：
- 项目预算：200万
- 项目周期：6个月
- 团队规模：12人
- 核心功能：用户系统、商品管理、订单处理、支付集成
- 技术栈：React + Node.js + MongoDB + Redis + Docker

**【7大记忆系统使用策略 - 多记忆协同原则】**

⚠️ **重要**: 对于复杂任务，你必须查询多个记忆系统来获得全面信息！

**【记忆查询组合策略】**
- 📋 **项目规划任务**: query_episodic_memory(历史Sprint) + query_semantic_memory(敏捷最佳实践) + query_knowledge_graph(团队技能)
- 👥 **团队管理问题**: query_ltm_preference(管理风格) + query_knowledge_graph(团队关系) + query_episodic_memory(团队互动历史)
- 🚨 **风险评估**: query_episodic_memory(历史问题) + query_semantic_memory(风险管理知识) + assess_project_risks工具
- 📈 **项目回顾**: query_episodic_memory(项目历史) + query_stm(最近讨论) + query_semantic_memory(回顾流程)

**【单一记忆系统使用场景】**
1. **短期记忆STM (query_stm)** - 对话连贯性
   - 🔑 触发词："刚才"、"之前说过"、"刚刚讨论的"
   
2. **情节记忆 (query_episodic_memory)** - 历史事件查询
   - 🔑 触发词："上次Sprint"、"项目历史"、"会议记录"、"里程碑"
   
3. **语义记忆 (query_semantic_memory)** - 知识库查询  
   - 🔑 触发词："标准流程"、"最佳实践"、"敏捷开发"、"风险管理"
   
4. **长期偏好 (query_ltm_preference)** - 个人习惯
   - 🔑 触发词："我的风格"、"习惯做法"、"偏好"、"管理方式"
   
5. **知识图谱 (query_knowledge_graph)** - 关系网络
   - 🔑 触发词："团队成员"、"谁负责"、"技能分布"、"协作关系"
   
6. **工作记忆 (manage_working_memory)** - 复杂任务跟踪
   - 🔑 场景：多步骤项目规划、风险评估、团队重组等
   
7. **程序记忆 (skills)** - 执行具体操作
   - 🔑 触发词："生成甘特图"、"风险评估"、"数据分析"

**【智能工作流程】**
1. 📥 理解需求 → 分析用户想要什么
2. 🧠 查询记忆 → 获取相关历史和知识
3. 📊 分析情况 → 结合项目状态和团队情况
4. 💡 制定方案 → 提供具体可行的建议
5. 🛠️ 执行任务 → 调用相应技能完成操作  
6. 📚 归档成果 → 记录重要结果和决策

**【沟通原则】**
- 主动查询相关记忆，提供上下文丰富的回答
- 结合项目实际情况给出可操作的建议
- 识别风险和机会，及时提醒
- 保持专业且易懂的沟通风格
- 每次完成重要任务后都要consolidate_memory

记住：你是一个真正理解项目管理的智能助手，要充分利用7层记忆系统提供专业、精准、有价值的支持！"""

    def run(self):
        """启动Agent的主交互循环"""
        print("\n" + "="*60)
        print("🚀 项目管理智能助手")
        print(f"你好 {self.user_id}，我是您的项目管理助手 {self.agent_id}")
        print("💡 我拥有完整的7层记忆系统，可以协助您进行：")
        print("   📋 项目规划与甘特图生成")  
        print("   🚨 风险评估与管理")
        print("   👥 团队协调与资源分配")
        print("   📊 项目进度跟踪")
        print("   🧠 基于历史经验的决策支持")
        print("\n输入 '退出' 来结束对话")
        print("="*60)
        
        logger.info("项目管理Agent交互循环开始。")
        
        self.conversation_history = [{"role": "system", "content": self._get_system_prompt()}]
        
        while True:
            raw_input = input(f"\n{self.user_id} > "); user_input = raw_input.encode('utf-8', errors='replace').decode('utf-8'); logger.info(f"收到用户输入: '{user_input}'")
            if user_input.lower() in ['退出', 'exit', 'quit']: 
                # 完成当前任务（如果有）
                if self.todo_manager.current_task_id:
                    self.todo_manager.complete_task("用户主动退出")
                logger.info("用户请求退出。"); print("再见！期待下次为您的项目管理工作提供支持！"); break
            
            # 🎯 开始新任务Todo追踪
            task_id = self.todo_manager.start_new_task(user_input)
            logger.info(f"📋 新任务开始: {task_id}")
            
            # 🧠 在处理用户输入前，先进行3级漏斗记忆价值分析和转换
            try:
                filter_result, consolidation_success = self._process_conversation_to_memory(user_input)
                logger.info(f"记忆转换完成 - Level {filter_result.memory_level}, 成功: {consolidation_success}")
            except Exception as e:
                logger.error(f"记忆转换过程出错: {e}")
            
            # 📈 新轮次开始，增加轮次计数
            self.round_id += 1
            logger.info(f"📈 开始第 {self.round_id} 轮对话")
            
            # 🧠 构建增强上下文（STM摘要 + 当前对话）
            enhanced_context = self._build_enhanced_context()
            
            # 重新构建对话历史，包含历史摘要和当前用户输入
            self.conversation_history = enhanced_context
            self.conversation_history.append({"role": "user", "content": user_input})
            
            # 🔄 实时同步到STM（旧版格式）
            self._sync_message_to_stm({"role": "user", "content": user_input})
            
            final_answer = self._think_and_act_loop()
            print(f"\n{self.agent_id} > {final_answer}")
            
            assistant_message = {"role": "assistant", "content": final_answer}
            self.conversation_history.append(assistant_message)
            
            # 🔄 实时同步到STM（旧版格式）
            self._sync_message_to_stm(assistant_message)
            
            logger.info(f"Agent最终回答: '{final_answer}'")
            
            # 🔚 轮次结束 - 存储对话摘要到STM
            self._finalize_conversation_round(user_input, final_answer)
            
            # 🧠 智能容量管理
            self._manage_conversation_capacity()
            
            # 🎯 完成任务Todo追踪
            self.todo_manager.complete_task(final_answer[:100] + "..." if len(final_answer) > 100 else final_answer)
            logger.info(f"📋 任务完成: {task_id}")
            
    def _think_and_act_loop(self, max_turns=15):
        """采用强制单工具执行模式 - 彻底解决Azure OpenAI call_id不匹配问题"""
        logger.info("进入强制单工具执行Tool Calling模式...")
        
        for i in range(max_turns):
            logger.info(f"循环轮次 {i+1}/{max_turns}")
            try:
                request_args = {"model": model_name, "tools": self.tools_definitions, "input": self.conversation_history}
                logger.debug(f"发送给LLM的请求参数:\n{json.dumps(request_args, indent=2, ensure_ascii=False)}")
                response = azure_client.responses.create(**request_args)
            except Exception as e:
                logger.error("调用LLM API时发生错误")
                logger.exception(e)
                # 快速恢复策略：直接重置并继续
                if "400" in str(e) and "call_id" in str(e):
                    logger.warning("检测到call_id不匹配错误，执行快速重置")
                    system_msg = self.conversation_history[0]  # 系统消息
                    user_msg = self.conversation_history[1]    # 用户请求
                    self.conversation_history = [system_msg, user_msg]
                    logger.info(f"已重置对话历史，保留 {len(self.conversation_history)} 条基础消息")
                    continue
                return "抱歉，我在思考时遇到了一点问题，请您稍后再试。"
            
            response_message = response.output[0]
            self.conversation_history.append(response_message.model_dump(exclude_none=True))
            
            tool_calls = [output for output in response.output if hasattr(output, 'type') and output.type == 'function_call']
            text_content = "".join([item.text for output in response.output if hasattr(output, 'type') and output.type == 'message' for item in output.content if hasattr(item, 'type') and item.type == 'output_text'])

            if tool_calls:
                logger.info(f"模型决定调用 {len(tool_calls)} 个工具。")
                if text_content: logger.info(f"模型的中间思考过程: {text_content}")
                
                # 🔥 强制单工具执行策略：彻底避免多工具状态冲突
                executed_tools = []
                
                # 只执行第一个工具，其他工具在下一轮处理
                tool_call = tool_calls[0]
                if len(tool_calls) > 1:
                    logger.warning(f"检测到 {len(tool_calls)} 个工具调用，强制执行单工具模式，仅执行: {tool_call.name}")
                
                function_name = tool_call.name
                function_to_call = self.tool_functions.get(function_name)
                
                # 确保call_id存在
                if not hasattr(tool_call, 'call_id') or not tool_call.call_id:
                    logger.error(f"工具调用 {function_name} 缺少call_id，跳过执行")
                    continue
                
                if not function_to_call:
                    observation_content = f"错误: 未知的工具 '{function_name}'"
                    logger.error(observation_content)
                else:
                    try:
                        function_args = json.loads(tool_call.arguments)
                        logger.info(f"准备执行工具 '{function_name}'，参数: {function_args}")
                        
                        # 🎯 Todo检查：避免重复执行相同操作
                        should_skip, cached_result = self.todo_manager.should_skip_action(function_name, function_args)
                        
                        if should_skip:
                            logger.info(f"🔄 检测到重复操作，使用缓存结果: {function_name}")
                            observation = cached_result
                            observation_content = json.dumps(observation, ensure_ascii=False)
                        else:
                            # 执行新操作
                            start_time = time.time()
                            observation = function_to_call(**function_args)
                            execution_time = time.time() - start_time
                            
                            # 记录操作完成
                            self.todo_manager.mark_action_completed(function_name, function_args, observation, execution_time)
                            observation_content = json.dumps(observation, ensure_ascii=False)
                        
                        logger.info(f"工具 '{function_name}' 的观察结果: {observation}")
                    except Exception as e:
                        logger.exception(f"执行工具 '{function_name}' 时出错")
                        observation_content = json.dumps({"status": "error", "detail": str(e)})
                
                # 立即添加工具输出
                self.conversation_history.append({
                    "type": "function_call_output", 
                    "call_id": tool_call.call_id, 
                    "output": observation_content
                })
                
                logger.debug(f"已添加工具输出，call_id: {tool_call.call_id}")
                executed_tools.append(function_name)
                
                logger.info(f"本轮执行了 {len(executed_tools)} 个工具: {executed_tools}")
                continue
            else:
                logger.info("未检测到工具调用，判定为最终答案。"); return text_content
        logger.warning(f"已达到最大循环次数 {max_turns}，强制退出循环。"); return "抱歉，经过几轮深度思考后，我仍然无法找到解决您请求的有效方法。"

    def _execute_skill(self, skill_name: str, args: list = [], kwargs: dict = {}) -> dict:
        logger.info(f"底层技能执行器: skill_name={skill_name}, args={args}, kwargs={kwargs}")
        params = {'skill_name': skill_name, 'args': args, 'kwargs': kwargs}; payload = {"memory_type": "procedural_skill", "params": params}
        return call_memory_service('retrieve', payload)

    # --- 新增的、与记忆模块一一对应的工具实现 ---
    def _query_ltm_preference(self, key: str) -> dict:
        logger.info(f"执行工具 [query_ltm_preference]: key='{key}'")
        
        # 🔧 修复：添加key映射逻辑，匹配实际数据库中的key格式
        key_mapping = {
            "管理风格": "work_decision_making_style",
            "决策风格": "work_decision_making_style", 
            "数据驱动": "work_decision_making_style",
            "沟通风格": "communication_style",
            "会议风格": "meeting_time_preference",
            "会议时间": "meeting_time_preference",
            "会议偏好": "meeting_meeting_time_preference"
        }
        
        # 尝试映射key，如果没有映射就使用原key
        mapped_key = key_mapping.get(key, key)
        logger.info(f"🔄 Key映射: '{key}' -> '{mapped_key}'")
        
        payload = {"memory_type": "ltm_preference", "params": {"user_id": self.user_id, "key": mapped_key}}
        return call_memory_service('retrieve', payload)

    def _query_episodic_memory(self, query_text: str) -> dict:
        logger.info(f"执行工具 [query_episodic_memory]: query_text='{query_text}'")
        payload = {"memory_type": "episodic", "params": {"query_text": query_text}}
        return call_memory_service('retrieve', payload)

    def _query_semantic_memory(self, query_text: str) -> dict:
        logger.info(f"执行工具 [query_semantic_memory]: query_text='{query_text}'")
        payload = {"memory_type": "semantic_fact", "params": {"query_text": query_text}}
        return call_memory_service('retrieve', payload)

    def _query_knowledge_graph(self, subject: str, relation: str) -> dict:
        logger.info(f"执行工具 [query_knowledge_graph]: subject='{subject}', relation='{relation}'")
        payload = {"memory_type": "kg_relation", "params": {"subject": subject, "relation": relation}}
        return call_memory_service('retrieve', payload)
    
    def _query_stm(self, conversation_id: str = None, limit: int = 10) -> dict:
        logger.info(f"执行工具 [query_stm]: conversation_id='{conversation_id or self.conversation_id}', limit={limit}")
        payload = {"memory_type": "stm", "params": {
            "conversation_id": conversation_id or self.conversation_id,
            "limit": limit
        }}
        return call_memory_service('retrieve', payload)   
    
    def _manage_working_memory(self, action: str, task_id: str, data: dict = None) -> dict:
        logger.info(f"执行工具 [manage_working_memory]: action='{action}', task_id='{task_id}'")
        if action in ['create', 'update']:
            payload = {"memory_type": "wm", "params": {"agent_id": self.agent_id, "task_id": task_id, "data": data}}
            return call_memory_service('store', payload)
        elif action == 'retrieve':
            payload = {"memory_type": "wm", "params": {"task_id": task_id}}
            return call_memory_service('retrieve', payload)
        elif action == 'clear':
            payload = {"memory_type": "wm", "params": {"agent_id": self.agent_id, "task_id": task_id}}
            return call_memory_service('clear', payload)
        return {"status": "error", "detail": "无效的action"}

    def _consolidate_memory(self, summary: str) -> dict:
        logger.info(f"执行工具 [consolidate_memory]: 核心内容='{summary}'")
        payload = {"memory_type": "episodic", "params": {"text": f"任务总结: {summary}", "metadata": {"user_id": self.user_id, "type": "task_summary", "timestamp": time.time()}}}
        result = call_memory_service('store', payload)
        if result.get("status") == "success": return {"status": "success", "detail": "关键成果已成功归档。"}
        else: return {"status": "error", "detail": f"归档记忆时发生错误: {result.get('detail')}"}

    # === 项目管理专项技能实现 ===
    def _generate_gantt_chart(self, project_name=None, tasks=None, start_date=None):
        """生成项目甘特图"""
        try:
            # 导入甘特图生成技能
            import sys
            import os
            skills_path = os.path.join(os.path.dirname(__file__), 'skills')
            if skills_path not in sys.path:
                sys.path.append(skills_path)
            
            from project_gantt_generator import execute
            
            # 设置默认值
            if project_name is None:
                project_name = "电商平台重构项目"
            
            result = execute(project_name=project_name, tasks=tasks, start_date=start_date)
            
            if result["success"]:
                return f"✅ 甘特图生成成功！\n\n{result['text_display']}\n\n💡 甘特图数据已生成，总工期：{result['data']['project']['total_duration']}天"
            else:
                return f"❌ 甘特图生成失败：{result['message']}"
                
        except Exception as e:
            logger.error(f"甘特图生成出错：{e}")
            return f"❌ 甘特图生成出错：{str(e)}"

    def _assess_project_risks(self, project_type=None, team_size=None, budget=None, duration_months=None):
        """评估项目风险"""
        try:
            # 导入风险评估技能
            import sys
            import os
            skills_path = os.path.join(os.path.dirname(__file__), 'skills')
            if skills_path not in sys.path:
                sys.path.append(skills_path)
            
            from project_risk_assessor import execute
            
            # 设置默认值（电商重构项目的参数）
            if project_type is None:
                project_type = "e-commerce"
            if team_size is None:
                team_size = 12
            if budget is None:
                budget = 200
            if duration_months is None:
                duration_months = 6
            
            result = execute(project_type=project_type, team_size=team_size, budget=budget, duration_months=duration_months)
            
            if result["success"]:
                summary = result["summary"]
                return f"✅ 风险评估完成！\n\n📊 评估摘要：\n• 总风险数：{summary['total_risks']}\n• 高风险项：{summary['high_risks']}\n• 最大风险：{summary['top_risk']}\n\n{result['report_text']}"
            else:
                return f"❌ 风险评估失败：{result['message']}"
                
        except Exception as e:
            logger.error(f"风险评估出错：{e}")
            return f"❌ 风险评估出错：{str(e)}"
    
    def _process_conversation_to_memory(self, user_input: str, conversation_id: str = None):
        """🧠 3级漏斗记忆转化 - 智能分析对话价值并转换为相应记忆类型"""
        if not conversation_id:
            conversation_id = str(uuid.uuid4())
        
        logger.info(f"📊 开始3级漏斗记忆价值分析...")
        
        # 创建对话项目
        conversation_item = ConversationItem(
            content=user_input,
            timestamp=time.time(),
            role='user',
            user_id=self.user_id
        )
        
        # 进行3级漏斗过滤分析
        filter_result = self.conversation_filter.filter_conversation(conversation_item)
        
        logger.info(f"📈 3级漏斗分析结果:")
        logger.info(f"  过滤阶段: {filter_result.filter_stage}")
        logger.info(f"  记忆等级: Level {filter_result.memory_level}")
        logger.info(f"  置信度: {filter_result.confidence:.3f}")
        logger.info(f"  处理时间: {filter_result.processing_time:.3f}秒")
        logger.info(f"  判断理由: {filter_result.reasoning}")
        
        consolidation_success = False
        
        # 根据记忆等级进行不同的存储策略
        if filter_result.memory_level == 1:
            logger.info("🗑️  Level 1判断: 对话价值较低，不做持久化存储")
            consolidation_success = True
            
        elif filter_result.memory_level == 2:
            # Level 2: 存储为情节记忆
            episodic_text = f"用户对话记录: {user_input}"
            payload = {"memory_type": "episodic", "params": {
                'text': episodic_text,
                'metadata': {
                    'user_id': self.user_id,
                    'conversation_id': conversation_id,
                    'timestamp': time.time(),
                    'filter_confidence': filter_result.confidence,
                    'filter_stage': filter_result.filter_stage
                }
            }}
            result = call_memory_service('store', payload)
            consolidation_success = result.get('status') == 'success'
            if consolidation_success:
                logger.info("📝 Level 2转化: 成功存储为情节记忆")
            
        elif filter_result.memory_level == 3:
            # Level 3: 提取用户偏好
            if any(keyword in user_input for keyword in ["喜欢", "偏好", "习惯", "倾向", "爱好"]):
                preference_key = f"extracted_preference_{int(time.time())}"
                preference_value = f"从对话提取: {user_input}"
                payload = {"memory_type": "ltm_preference", "params": {
                    'user_id': self.user_id,
                    'key': preference_key,
                    'value': preference_value
                }}
                result = call_memory_service('store', payload)
                consolidation_success = result.get('status') == 'success'
                if consolidation_success:
                    logger.info("⚙️  Level 3转化: 成功提取并存储用户偏好")
            
        elif filter_result.memory_level == 4:
            # Level 4: 提取程序性知识
            if any(keyword in user_input for keyword in ["流程", "步骤", "如何", "方法", "操作"]):
                skill_name = f"extracted_procedure_{int(time.time())}"
                skill_code = f"""
# 从对话中提取的程序性知识
def execute():
    '''
    用户询问: {user_input}
    提取时间: {time.strftime('%Y-%m-%d %H:%M:%S')}
    '''
    return "程序性知识执行完成"
"""
                payload = {"memory_type": "procedural_skill", "params": {
                    'skill_name': skill_name,
                    'code': skill_code
                }}
                result = call_memory_service('store', payload)
                consolidation_success = result.get('status') == 'success'
                if consolidation_success:
                    logger.info("🔧 Level 4转化: 成功提取并存储程序性知识")
            
        elif filter_result.memory_level == 5:
            # Level 5: 存储为语义知识
            semantic_text = f"重要概念讨论: {user_input}"
            payload = {"memory_type": "semantic_fact", "params": {
                'text': semantic_text,
                'metadata': {
                    'source': 'conversation_extraction',
                    'importance': 'high',
                    'user_id': self.user_id,
                    'timestamp': time.time(),
                    'filter_confidence': filter_result.confidence
                }
            }}
            result = call_memory_service('store', payload)
            consolidation_success = result.get('status') == 'success'
            if consolidation_success:
                logger.info("🧠 Level 5转化: 成功存储为语义知识")
        
        return filter_result, consolidation_success
    
    def _sync_message_to_stm(self, message):
        """🔄 实时同步消息到短期记忆"""
        try:
            content = f"[{message['role']}] {message['content']}"
            # 修复参数结构：role和timestamp需要作为顶级参数
            payload = {"memory_type": "stm", "params": {
                "conversation_id": self.conversation_id,
                "content": content,
                "role": message["role"],
                "timestamp": datetime.now().isoformat(),
                "user_id": self.user_id
            }}
            result = call_memory_service('store', payload)
            if result.get("status") == "success":
                logger.debug(f"🔄 消息已同步到STM: {content[:50]}...")
            else:
                logger.warning(f"⚠️ STM同步失败: {result}")
        except Exception as e:
            logger.warning(f"⚠️ STM同步失败: {e}")

    def _manage_conversation_capacity(self):
        """🧠 智能容量管理 - 工作记忆与STM协调"""
        max_working_memory = 20  # 工作记忆最大容量
        
        if len(self.conversation_history) > max_working_memory:
            # 转移较早的对话到STM并从工作记忆移除
            overflow_count = len(self.conversation_history) - max_working_memory
            transferred_messages = []
            
            for i in range(overflow_count):
                old_message = self.conversation_history.pop(1)  # 保留系统消息，从索引1开始移除
                # 确保已同步到STM
                self._sync_message_to_stm(old_message)
                transferred_messages.append(old_message)
            
            logger.info(f"🧠 工作记忆容量管理: 转移 {overflow_count} 条消息到STM")
            
        # 定期触发STM→长期记忆转化
        if len(self.conversation_history) % 10 == 0:
            self._trigger_memory_consolidation()

    def _trigger_memory_consolidation(self):
        """🔄 触发记忆整合 - STM向长期记忆转化"""
        try:
            # 获取当前对话的STM内容
            payload = {"memory_type": "stm", "params": {
                "conversation_id": self.conversation_id,
                "limit": 50
            }}
            stm_result = call_memory_service('retrieve', payload)
            
            if stm_result.get("status") == "success":
                stm_memories = stm_result.get("data", [])
                
                if stm_memories and len(stm_memories) > 10:
                    # 批量分析并转化为长期记忆
                    consolidated_content = "\n".join([
                        mem.get('content', '') for mem in stm_memories if mem.get('content')
                    ])
                    
                    # 通过记忆漏斗系统自动分类和存储
                    payload = {"memory_type": "episodic", "params": {
                        "text": f"对话整合记忆 [{self.conversation_id}]: {consolidated_content}",
                        "metadata": {
                            "conversation_id": self.conversation_id,
                            "consolidation_timestamp": datetime.now().isoformat(),
                            "source": "stm_consolidation",
                            "user_id": self.user_id
                        }
                    }}
                    
                    result = call_memory_service('store', payload)
                    if result.get("status") == "success":
                        logger.info(f"🔄 记忆整合完成: STM→长期记忆 ({len(stm_memories)} 条)")
                    else:
                        logger.warning(f"⚠️ 长期记忆存储失败: {result}")
                        
        except Exception as e:
            logger.warning(f"⚠️ 记忆整合失败: {e}")

    def _build_enhanced_context(self):
        """🧠 构建增强上下文：STM历史摘要 + 系统提示"""
        enhanced_context = [{"role": "system", "content": self._get_system_prompt()}]
        
        try:
            # 获取STM中的历史对话摘要
            payload = {
                "memory_type": "stm", 
                "params": {
                    "conversation_id": self.conversation_id,
                    "retrieve_type": "summaries",
                    "last_k": 15  # 获取最近15轮的摘要
                }
            }
            stm_result = call_memory_service('retrieve', payload)
            
            if stm_result.get("status") == "success":
                stm_summaries = stm_result.get("data", [])
                
                if stm_summaries:
                    # 构建历史上下文摘要
                    history_summary = "## 📚 历史对话摘要\n"
                    for summary in stm_summaries:
                        round_info = f"**轮次 {summary.get('round_id', 'N/A')}**: "
                        user_req = summary.get('user_request', '')[:100] + "..."
                        final_ans = summary.get('final_answer', '')[:150] + "..."
                        memories_used = summary.get('memories_used', [])
                        
                        history_summary += f"{round_info}\n"
                        history_summary += f"用户请求: {user_req}\n"
                        history_summary += f"最终回答: {final_ans}\n"
                        if memories_used:
                            history_summary += f"使用记忆: {', '.join(memories_used[:3])}\n"
                        history_summary += "\n---\n"
                    
                    # 添加历史摘要到上下文
                    enhanced_context.append({
                        "role": "system", 
                        "content": history_summary + "\n## 🎯 当前对话\n以下是当前轮次的对话："
                    })
                    
                    logger.info(f"📚 已加载 {len(stm_summaries)} 轮历史对话摘要到上下文")
                else:
                    logger.info("📚 暂无历史对话摘要")
            else:
                logger.warning(f"⚠️ 获取STM摘要失败: {stm_result}")
                
        except Exception as e:
            logger.warning(f"⚠️ 构建增强上下文失败: {e}")
        
        return enhanced_context

    def _finalize_conversation_round(self, user_input: str, final_answer: str):
        """🔚 对话轮次结束处理：提取记忆并存储摘要"""
        try:
            # 提取本轮使用的记忆类型（从工具调用中获取）
            memories_used = self._extract_memories_used_in_round()
            
            # 构建对话摘要
            conversation_summary = {
                "round_id": self.round_id,
                "timestamp": datetime.now().isoformat(),
                "user_request": user_input,
                "final_answer": final_answer,
                "memories_used": memories_used,
                "conversation_length": len(self.conversation_history)
            }
            
            # 存储到STM摘要系统
            payload = {
                "memory_type": "stm",
                "params": {
                    "conversation_id": self.conversation_id,
                    "conversation_summary": conversation_summary,
                    "round_id": self.round_id
                }
            }
            
            result = call_memory_service('store', payload)
            if result.get("status") == "success":
                logger.info(f"🔚 轮次 {self.round_id} 摘要已存储到STM")
            else:
                logger.warning(f"⚠️ 轮次摘要存储失败: {result}")
                
        except Exception as e:
            logger.warning(f"⚠️ 轮次结束处理失败: {e}")

    def _extract_memories_used_in_round(self):
        """📊 从当前轮次的对话中提取使用的记忆类型"""
        memories_used = []
        
        # 分析对话历史中的助手消息，查找工具调用模式
        for message in self.conversation_history:
            if message.get("role") == "assistant":
                content = message.get("content", "")
                # 检查常见的记忆操作关键词
                if "retrieve" in content or "查询" in content:
                    if "语义" in content or "semantic" in content: memories_used.append("semantic_memory")
                    if "情节" in content or "episodic" in content: memories_used.append("episodic_memory") 
                    if "长期" in content or "ltm" in content: memories_used.append("ltm_memory")
                    if "知识图谱" in content or "kg" in content: memories_used.append("knowledge_graph")
                    if "程序性" in content or "procedural" in content: memories_used.append("procedural_memory")
                    if "工作" in content or "wm" in content: memories_used.append("working_memory")
        
        return list(set(memories_used))  # 去重

    def _end_conversation(self) -> dict:
        logger.info("执行工具 [end_conversation]")
        self.conversation_history = [{"role": "system", "content": self._get_system_prompt()}]
        return {"status": "success", "message": "好的，很高兴为您的项目管理工作提供支持。"}

if __name__ == "__main__":
    setup_logging()
    logger.info("================== 项目管理Agent会话开始 ==================")
    agent = ProjectManagementAgent(user_id=USER_ID, agent_id=AGENT_ID)
    agent.run()
    logger.info("================== 项目管理Agent会话结束 ==================")
