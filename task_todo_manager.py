# -*- coding: utf-8 -*-
"""
任务Todo追踪管理器
用于记录和追踪每个任务的执行计划，避免重复执行相同的操作
"""
import os
import json
import hashlib
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)

class TaskTodoManager:
    """任务Todo管理器 - 避免重复执行相同操作"""
    
    def __init__(self, workspace_dir: str = "."):
        self.workspace_dir = workspace_dir
        self.todo_file = os.path.join(workspace_dir, "current_task_todo.md")
        self.completed_actions_file = os.path.join(workspace_dir, "completed_actions.json")
        self.current_task_id = None
        self.completed_actions = self._load_completed_actions()
        
    def _load_completed_actions(self) -> Dict[str, Any]:
        """加载已完成的操作记录"""
        if os.path.exists(self.completed_actions_file):
            try:
                with open(self.completed_actions_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"加载completed_actions失败: {e}")
        return {}
    
    def _save_completed_actions(self):
        """保存已完成的操作记录"""
        try:
            with open(self.completed_actions_file, 'w', encoding='utf-8') as f:
                json.dump(self.completed_actions, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存completed_actions失败: {e}")
    
    def _generate_action_hash(self, tool_name: str, params: Dict) -> str:
        """生成操作的唯一哈希值"""
        # 将参数排序后序列化，确保相同参数生成相同hash
        sorted_params = json.dumps(params, sort_keys=True, ensure_ascii=False)
        action_str = f"{tool_name}|{sorted_params}"
        return hashlib.md5(action_str.encode('utf-8')).hexdigest()[:12]
    
    def start_new_task(self, task_description: str, initial_plan: List[str] = None) -> str:
        """开始新任务，创建todo.md文件"""
        self.current_task_id = f"task_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # 重置当前任务的completed_actions
        self.completed_actions = {
            "task_id": self.current_task_id,
            "task_description": task_description,
            "started_at": datetime.now().isoformat(),
            "actions": {}
        }
        
        # 创建todo.md文件
        todo_content = f"""# 当前任务 Todo 追踪

## 任务信息
- **任务ID**: {self.current_task_id}
- **任务描述**: {task_description}
- **开始时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## 计划步骤
"""
        
        if initial_plan:
            for i, step in enumerate(initial_plan, 1):
                todo_content += f"{i}. [ ] {step}\n"
        else:
            todo_content += "1. [ ] 分析任务需求\n2. [ ] 制定执行计划\n3. [ ] 逐步执行\n"
        
        todo_content += f"""
## 已执行操作记录
*(自动更新)*

---
*此文件由TaskTodoManager自动维护，任务完成后会被重置*
"""
        
        with open(self.todo_file, 'w', encoding='utf-8') as f:
            f.write(todo_content)
        
        logger.info(f"新任务开始: {self.current_task_id} - {task_description}")
        return self.current_task_id
    
    def check_action_completed(self, tool_name: str, params: Dict) -> Optional[Dict]:
        """检查某个操作是否已经完成"""
        action_hash = self._generate_action_hash(tool_name, params)
        
        if action_hash in self.completed_actions.get("actions", {}):
            action_record = self.completed_actions["actions"][action_hash]
            logger.info(f"🔄 检测到重复操作: {tool_name} - 使用缓存结果")
            return action_record
        
        return None
    
    def mark_action_completed(self, tool_name: str, params: Dict, result: Any, execution_time: float = 0):
        """标记某个操作为已完成"""
        action_hash = self._generate_action_hash(tool_name, params)
        
        action_record = {
            "tool_name": tool_name,
            "params": params,
            "result": result,
            "completed_at": datetime.now().isoformat(),
            "execution_time": execution_time,
            "hash": action_hash
        }
        
        self.completed_actions["actions"][action_hash] = action_record
        self._save_completed_actions()
        
        # 更新todo.md文件
        self._update_todo_file(tool_name, params, result)
        
        logger.info(f"✅ 操作已完成并记录: {tool_name}")
    
    def _update_todo_file(self, tool_name: str, params: Dict, result: Any):
        """更新todo.md文件的已执行操作记录"""
        if not os.path.exists(self.todo_file):
            return
        
        try:
            with open(self.todo_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 在"已执行操作记录"部分添加新记录
            time_str = datetime.now().strftime('%H:%M:%S')
            params_str = json.dumps(params, ensure_ascii=False, separators=(',', ':'))
            new_record = f"- **{time_str}** `{tool_name}` {params_str}\n"
            
            # 查找插入位置
            if "## 已执行操作记录" in content:
                parts = content.split("## 已执行操作记录")
                if len(parts) == 2:
                    before = parts[0] + "## 已执行操作记录\n*(自动更新)*\n\n"
                    after_lines = parts[1].split('\n')
                    # 保留第一行的说明，然后插入新记录
                    after = new_record + '\n'.join(after_lines[2:])
                    content = before + after
            
            with open(self.todo_file, 'w', encoding='utf-8') as f:
                f.write(content)
                
        except Exception as e:
            logger.error(f"更新todo.md失败: {e}")
    
    def add_plan_step(self, step_description: str):
        """动态添加计划步骤"""
        if not os.path.exists(self.todo_file):
            return
        
        try:
            with open(self.todo_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 在计划步骤部分添加新步骤
            if "## 计划步骤" in content and "## 已执行操作记录" in content:
                parts = content.split("## 已执行操作记录")
                plan_part = parts[0]
                record_part = "## 已执行操作记录" + parts[1]
                
                # 计算现有步骤数量
                step_count = plan_part.count(". [ ]") + plan_part.count(". [x]")
                new_step = f"{step_count + 1}. [ ] {step_description}\n"
                
                # 在计划步骤后添加
                plan_part += f"\n{new_step}"
                content = plan_part + "\n" + record_part
            
            with open(self.todo_file, 'w', encoding='utf-8') as f:
                f.write(content)
                
        except Exception as e:
            logger.error(f"添加计划步骤失败: {e}")
    
    def complete_task(self, task_summary: str = ""):
        """完成当前任务，清理todo文件"""
        if self.current_task_id:
            logger.info(f"任务完成: {self.current_task_id}")
            
            # 记录任务完成
            self.completed_actions["completed_at"] = datetime.now().isoformat()
            self.completed_actions["task_summary"] = task_summary
            self._save_completed_actions()
            
            # 归档todo文件
            if os.path.exists(self.todo_file):
                archive_name = f"completed_task_{self.current_task_id}.md"
                archive_path = os.path.join(self.workspace_dir, archive_name)
                try:
                    os.rename(self.todo_file, archive_path)
                    logger.info(f"Todo文件已归档: {archive_name}")
                except Exception as e:
                    logger.error(f"归档todo文件失败: {e}")
            
            # 重置状态
            self.current_task_id = None
            self.completed_actions = {}
    
    def get_task_progress(self) -> Dict:
        """获取当前任务进度"""
        return {
            "task_id": self.current_task_id,
            "completed_actions_count": len(self.completed_actions.get("actions", {})),
            "actions": list(self.completed_actions.get("actions", {}).keys())
        }
    
    def should_skip_action(self, tool_name: str, params: Dict) -> tuple[bool, Optional[Dict]]:
        """判断是否应该跳过某个操作（已完成且结果有效）"""
        cached_result = self.check_action_completed(tool_name, params)
        
        if cached_result:
            # 检查结果是否仍然有效（例如，可以添加时间检查等逻辑）
            result = cached_result.get("result")
            if result and result.get("status") == "success":
                return True, result
        
        return False, None


# 使用示例和测试
if __name__ == "__main__":
    # 设置日志
    logging.basicConfig(level=logging.INFO)
    
    # 创建管理器
    todo_manager = TaskTodoManager("/tmp/test_todo")
    
    # 开始新任务
    task_id = todo_manager.start_new_task(
        "安排四平出差",
        ["查询上次出差记录", "预订航班", "计算预算", "安排酒店"]
    )
    
    # 模拟操作执行
    params1 = {"destination": "四平", "preference": "早班商务舱靠窗"}
    
    # 第一次执行
    should_skip, cached = todo_manager.should_skip_action("book_flight", params1)
    print(f"第一次执行 - 跳过: {should_skip}")
    
    if not should_skip:
        result = {"status": "success", "data": "已预订CA1846"}
        todo_manager.mark_action_completed("book_flight", params1, result)
    
    # 第二次相同参数 - 应该跳过
    should_skip, cached = todo_manager.should_skip_action("book_flight", params1)
    print(f"第二次执行 - 跳过: {should_skip}, 缓存结果: {cached}")
    
    # 完成任务
    todo_manager.complete_task("四平出差安排完成")
