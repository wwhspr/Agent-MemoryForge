
def get_skill_metadata():
    """获取技能元数据"""
    return {
        "name": "book_flight",
        "description": "Execute book flight related tasks",
        "parameters": ['destination', 'preference']
    }


def execute(destination, preference):
    # 模拟航班预订逻辑
    if "靠窗" in preference:
        seat_type = "靠窗座位"
    else:
        seat_type = "过道座位"
    
    flight_no = f"CA{1800 + hash(destination) % 200}"
    return f"已为您预订{destination}航班 {flight_no}，{seat_type}"
