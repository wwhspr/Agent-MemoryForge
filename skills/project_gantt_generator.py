#!/usr/bin/env python3
"""
项目管理技能：生成甘特图
为项目管理助手提供生成项目甘特图的能力
"""

from datetime import datetime, timedelta
import json

def generate_gantt_chart(project_name, tasks, start_date=None):
    """
    生成项目甘特图数据
    
    Args:
        project_name (str): 项目名称
        tasks (list): 任务列表，每个任务包含name, duration, dependencies
        start_date (str): 项目开始日期，格式YYYY-MM-DD
    
    Returns:
        dict: 甘特图数据结构
    """
    if start_date is None:
        start_date = datetime.now().strftime("%Y-%m-%d")
    
    # 默认任务模板（如果没有提供具体任务）
    default_tasks = [
        {"name": "需求分析", "duration": 10, "dependencies": []},
        {"name": "技术方案设计", "duration": 7, "dependencies": ["需求分析"]},
        {"name": "前端开发", "duration": 20, "dependencies": ["技术方案设计"]},
        {"name": "后端开发", "duration": 25, "dependencies": ["技术方案设计"]},
        {"name": "集成测试", "duration": 10, "dependencies": ["前端开发", "后端开发"]},
        {"name": "用户验收测试", "duration": 5, "dependencies": ["集成测试"]},
        {"name": "部署上线", "duration": 3, "dependencies": ["用户验收测试"]}
    ]
    
    if not tasks:
        tasks = default_tasks
    
    # 计算任务开始和结束日期
    task_schedule = {}
    project_start = datetime.strptime(start_date, "%Y-%m-%d")
    
    def calculate_task_start(task_name):
        """递归计算任务开始时间"""
        if task_name in task_schedule:
            return task_schedule[task_name]["start"]
        
        # 找到对应的任务
        task = next((t for t in tasks if t["name"] == task_name), None)
        if not task:
            return project_start
        
        # 如果没有依赖，从项目开始日期开始
        dependencies = task.get("dependencies", [])
        if not dependencies:
            start_time = project_start
        else:
            # 计算所有依赖任务的最晚结束时间
            max_end_time = project_start
            for dep in dependencies:
                dep_start = calculate_task_start(dep)
                dep_task = next((t for t in tasks if t["name"] == dep), None)
                if dep_task:
                    dep_end = dep_start + timedelta(days=dep_task["duration"])
                    if dep_end > max_end_time:
                        max_end_time = dep_end
            start_time = max_end_time
        
        end_time = start_time + timedelta(days=task["duration"])
        
        task_schedule[task_name] = {
            "start": start_time,
            "end": end_time,
            "duration": task["duration"]
        }
        
        return start_time
    
    # 计算所有任务的时间安排
    for task in tasks:
        calculate_task_start(task["name"])
    
    # 生成甘特图数据
    gantt_data = {
        "project": {
            "name": project_name,
            "start_date": start_date,
            "total_duration": 0
        },
        "tasks": [],
        "critical_path": [],
        "milestones": []
    }
    
    # 计算项目总工期
    if task_schedule:
        project_end = max(schedule["end"] for schedule in task_schedule.values())
        gantt_data["project"]["total_duration"] = (project_end - project_start).days
        gantt_data["project"]["end_date"] = project_end.strftime("%Y-%m-%d")
    
    # 添加任务详情
    for task in tasks:
        if task["name"] in task_schedule:
            schedule = task_schedule[task["name"]]
            gantt_data["tasks"].append({
                "name": task["name"],
                "start_date": schedule["start"].strftime("%Y-%m-%d"),
                "end_date": schedule["end"].strftime("%Y-%m-%d"),
                "duration": task["duration"],
                "dependencies": task.get("dependencies", []),
                "progress": 0  # 默认进度0%
            })
    
    # 识别里程碑（关键任务完成点）
    milestone_tasks = ["需求分析", "技术方案设计", "集成测试", "部署上线"]
    for task_name in milestone_tasks:
        if task_name in task_schedule:
            gantt_data["milestones"].append({
                "name": f"{task_name}完成",
                "date": task_schedule[task_name]["end"].strftime("%Y-%m-%d"),
                "type": "milestone"
            })
    
    return gantt_data

def generate_gantt_chart_text(gantt_data):
    """
    生成甘特图的文本表示
    
    Args:
        gantt_data (dict): 甘特图数据
    
    Returns:
        str: 甘特图的文本表示
    """
    text_output = []
    text_output.append(f"📊 项目甘特图: {gantt_data['project']['name']}")
    text_output.append("=" * 60)
    text_output.append(f"🗓️  项目周期: {gantt_data['project']['start_date']} ~ {gantt_data['project']['end_date']}")
    text_output.append(f"⏱️  总工期: {gantt_data['project']['total_duration']} 天")
    text_output.append("")
    
    text_output.append("📋 任务时间表:")
    text_output.append("-" * 40)
    
    for i, task in enumerate(gantt_data['tasks'], 1):
        text_output.append(f"{i:2d}. {task['name']}")
        text_output.append(f"     📅 {task['start_date']} ~ {task['end_date']} ({task['duration']}天)")
        if task['dependencies']:
            text_output.append(f"     🔗 依赖: {', '.join(task['dependencies'])}")
        text_output.append("")
    
    if gantt_data['milestones']:
        text_output.append("🏁 项目里程碑:")
        text_output.append("-" * 40)
        for milestone in gantt_data['milestones']:
            text_output.append(f"• {milestone['name']}: {milestone['date']}")
        text_output.append("")
    
    # 添加可视化时间轴（简化版）
    text_output.append("📈 时间轴预览:")
    text_output.append("-" * 40)
    
    # 计算时间轴的周数
    start_date = datetime.strptime(gantt_data['project']['start_date'], "%Y-%m-%d")
    weeks = (gantt_data['project']['total_duration'] + 6) // 7  # 向上取整到周
    
    for task in gantt_data['tasks'][:5]:  # 只显示前5个任务
        task_start = datetime.strptime(task['start_date'], "%Y-%m-%d")
        task_end = datetime.strptime(task['end_date'], "%Y-%m-%d")
        
        start_week = (task_start - start_date).days // 7
        end_week = (task_end - start_date).days // 7
        
        timeline = [" "] * weeks
        for week in range(start_week, min(end_week + 1, weeks)):
            timeline[week] = "█"
        
        text_output.append(f"{task['name'][:15]:15s} |{''.join(timeline)}|")
    
    # 添加周数标记
    week_markers = "".join([str(i % 10) for i in range(weeks)])
    text_output.append(" " * 16 + "|" + week_markers + "|")
    text_output.append(" " * 16 + "(周数)")
    
    return "\n".join(text_output)

# 技能主函数
def execute(project_name="电商平台重构项目", tasks=None, start_date=None):
    """
    执行甘特图生成技能
    
    Args:
        project_name (str): 项目名称
        tasks (list): 任务列表
        start_date (str): 开始日期
    
    Returns:
        dict: 包含甘特图数据和文本展示的结果
    """
    try:
        # 生成甘特图数据
        gantt_data = generate_gantt_chart(project_name, tasks, start_date)
        
        # 生成文本表示
        text_chart = generate_gantt_chart_text(gantt_data)
        
        return {
            "success": True,
            "data": gantt_data,
            "text_display": text_chart,
            "message": f"成功生成项目 '{project_name}' 的甘特图"
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "message": "甘特图生成失败"
        }

if __name__ == "__main__":
    # 测试代码
    result = execute()
    if result["success"]:
        print(result["text_display"])
    else:
        print(f"错误: {result['error']}")
