
def get_skill_metadata():
    """获取技能元数据"""
    return {
        "name": "generate_itinerary",
        "description": "Execute generate itinerary related tasks",
        "parameters": ['task_data_json']
    }


import json
def execute(task_data_json):
    task_data = json.loads(task_data_json)
    results = task_data.get('results', {})
    # 从任务的根级别获取目的地，而不是从results中获取
    destination = task_data.get('destination', '未知')
    itinerary = f"""
========================================
      商务行程单 (任务ID: {task_data.get('task_id')})
========================================
目的地: {destination}
航班号: {results.get('flight_confirmation', '待定')} (偏好: {results.get('flight_preference', '无')})
酒店: {results.get('hotel_confirmation', '待定')}
晚宴地点: {results.get('dinner_location', '待定')}
备注: {results.get('notes', '无')}
----------------------------------------
"""
    return itinerary
