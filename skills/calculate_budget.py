
def get_skill_metadata():
    """获取技能元数据"""
    return {
        "name": "calculate_budget",
        "description": "Execute calculate budget related tasks",
        "parameters": {
            "type": "object",
            "properties": {
                "days_str": {
                    "type": "string",
                    "description": "出差天数，如 '3天'"
                },
                "hotel_level": {
                    "type": "string",
                    "description": "酒店级别，可选：5star, 4star, 3star",
                    "default": "5star"
                }
            },
            "required": ["days_str"]
        }
    }


import json
import re

def execute(days_str, hotel_level="5star"):
    # 从字符串中提取数字，支持 "3天" 或 "3" 格式
    days_match = re.search(r'\d+', str(days_str))
    if days_match:
        days = int(days_match.group())
    else:
        days = 3  # 默认值
    
    # 预算标准
    flight_cost = 1200  # 经济舱往返
    hotel_costs = {"5star": 800, "4star": 500, "3star": 300}
    meal_cost_per_day = 300
    transport_cost = 200
    
    hotel_cost = hotel_costs.get(hotel_level, 800) * days
    meal_cost = meal_cost_per_day * days
    total = flight_cost + hotel_cost + meal_cost + transport_cost
    
    return f"""
💰 差旅预算计算 (共{days}天):
  ✈️  机票: ¥{flight_cost}
  🏨 酒店: ¥{hotel_cost} ({hotel_level}, ¥{hotel_costs.get(hotel_level, 800)}/晚)
  🍽️  餐费: ¥{meal_cost} (¥{meal_cost_per_day}/天)
  🚗 交通: ¥{transport_cost}
  ─────────────────
  💳 总计: ¥{total}
"""
