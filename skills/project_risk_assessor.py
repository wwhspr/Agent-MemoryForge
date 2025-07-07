#!/usr/bin/env python3
"""
项目管理技能：风险评估报告生成器
为项目管理助手提供生成项目风险评估报告的能力
"""

from datetime import datetime
import json

def assess_project_risks(project_type="e-commerce", team_size=12, budget=2000000, duration_months=6):
    """
    评估项目风险
    
    Args:
        project_type (str): 项目类型
        team_size (int): 团队规模
        budget (int): 项目预算
        duration_months (int): 项目周期（月）
    
    Returns:
        dict: 风险评估结果
    """
    
    # 定义风险数据库
    risk_database = {
        "e-commerce": [
            {
                "name": "需求变更频繁",
                "category": "需求风险",
                "base_probability": 0.8,
                "impact": "高",
                "description": "电商项目业务需求变化快，可能导致频繁的需求变更"
            },
            {
                "name": "第三方API不稳定",
                "category": "技术风险", 
                "base_probability": 0.6,
                "impact": "中",
                "description": "依赖支付、物流等第三方API，存在服务不稳定风险"
            },
            {
                "name": "性能压测不达标",
                "category": "技术风险",
                "base_probability": 0.4,
                "impact": "高",
                "description": "高并发场景下系统性能可能不达标"
            },
            {
                "name": "数据迁移风险",
                "category": "技术风险",
                "base_probability": 0.3,
                "impact": "高", 
                "description": "从旧系统迁移数据可能出现数据丢失或不一致"
            },
            {
                "name": "安全漏洞",
                "category": "安全风险",
                "base_probability": 0.2,
                "impact": "极高",
                "description": "支付和用户数据安全漏洞风险"
            },
            {
                "name": "关键人员离职",
                "category": "人员风险",
                "base_probability": 0.15,
                "impact": "高",
                "description": "核心技术人员离职影响项目进度"
            },
            {
                "name": "预算超支",
                "category": "管理风险",
                "base_probability": 0.25,
                "impact": "中",
                "description": "项目复杂度超预期导致预算超支"
            }
        ]
    }
    
    # 获取项目相关风险
    project_risks = risk_database.get(project_type, [])
    
    # 根据项目特征调整风险概率
    assessed_risks = []
    for risk in project_risks:
        adjusted_risk = risk.copy()
        probability = risk["base_probability"]
        
        # 根据团队规模调整
        if team_size > 15:
            if risk["category"] == "人员风险":
                probability += 0.1  # 大团队沟通风险增加
        elif team_size < 8:
            if risk["category"] == "技术风险":
                probability += 0.15  # 小团队技术风险增加
        
        # 根据项目周期调整
        if duration_months > 12:
            if risk["category"] in ["需求风险", "人员风险"]:
                probability += 0.2  # 长项目需求和人员风险增加
        elif duration_months < 3:
            if risk["category"] == "技术风险":
                probability += 0.25  # 短期项目技术风险增加
        
        # 根据预算调整
        if budget < 1000000:
            if risk["category"] == "技术风险":
                probability += 0.1  # 预算紧张技术风险增加
        
        # 确保概率在合理范围内
        probability = min(max(probability, 0.05), 0.95)
        adjusted_risk["probability"] = round(probability, 2)
        
        # 计算风险值（概率×影响）
        impact_score = {"低": 1, "中": 2, "高": 3, "极高": 4}
        risk_score = probability * impact_score.get(risk["impact"], 2)
        adjusted_risk["risk_score"] = round(risk_score, 2)
        
        assessed_risks.append(adjusted_risk)
    
    # 按风险值排序
    assessed_risks.sort(key=lambda x: x["risk_score"], reverse=True)
    
    return assessed_risks

def generate_risk_mitigation_strategies(risks):
    """
    生成风险缓解策略
    
    Args:
        risks (list): 评估的风险列表
    
    Returns:
        dict: 风险缓解策略
    """
    
    mitigation_strategies = {
        "需求变更频繁": [
            "建立需求变更管理流程，设置变更审批机制",
            "采用敏捷开发方法，分阶段交付降低变更影响",
            "与业务方签署需求冻结协议，明确变更成本"
        ],
        "第三方API不稳定": [
            "实施API监控和自动重试机制",
            "准备备用API服务商，建立双重保障",
            "设计降级方案，确保核心功能可用"
        ],
        "性能压测不达标": [
            "在开发早期进行性能基准测试",
            "设计可扩展架构，支持水平扩展", 
            "定期进行性能评估和优化"
        ],
        "数据迁移风险": [
            "制定详细的数据迁移计划和回滚方案",
            "先在测试环境充分验证迁移脚本",
            "采用分批迁移策略，降低影响范围"
        ],
        "安全漏洞": [
            "集成安全扫描工具到CI/CD流程",
            "定期进行渗透测试和安全审计",
            "建立安全事件响应机制"
        ],
        "关键人员离职": [
            "建立知识文档化制度，避免知识孤岛",
            "实施结对编程，确保知识共享",
            "准备人员备份计划，培养多技能人才"
        ],
        "预算超支": [
            "建立项目成本监控机制，定期评估",
            "设置预算警戒线，提前预警",
            "制定范围调整预案，确保核心功能交付"
        ]
    }
    
    strategies = {}
    for risk in risks:
        if risk["name"] in mitigation_strategies:
            strategies[risk["name"]] = mitigation_strategies[risk["name"]]
    
    return strategies

def generate_risk_report_text(risks, strategies, project_info):
    """
    生成风险评估报告的文本格式
    
    Args:
        risks (list): 风险列表
        strategies (dict): 缓解策略
        project_info (dict): 项目信息
    
    Returns:
        str: 风险评估报告文本
    """
    
    report = []
    report.append("🚨 项目风险评估报告")
    report.append("=" * 60)
    report.append(f"📊 项目信息:")
    report.append(f"   • 项目类型: {project_info.get('type', 'N/A')}")
    report.append(f"   • 团队规模: {project_info.get('team_size', 'N/A')} 人")
    report.append(f"   • 项目预算: {project_info.get('budget', 'N/A')} 万元")
    report.append(f"   • 项目周期: {project_info.get('duration', 'N/A')} 个月")
    report.append(f"   • 评估时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    report.append("")
    
    # 风险等级分类
    high_risks = [r for r in risks if r["risk_score"] >= 2.0]
    medium_risks = [r for r in risks if 1.0 <= r["risk_score"] < 2.0]
    low_risks = [r for r in risks if r["risk_score"] < 1.0]
    
    report.append("📈 风险等级分布:")
    report.append(f"   🔴 高风险: {len(high_risks)} 项")
    report.append(f"   🟡 中风险: {len(medium_risks)} 项") 
    report.append(f"   🟢 低风险: {len(low_risks)} 项")
    report.append("")
    
    # 详细风险分析
    report.append("🔍 详细风险分析:")
    report.append("-" * 40)
    
    for i, risk in enumerate(risks, 1):
        # 风险等级图标
        if risk["risk_score"] >= 2.0:
            risk_icon = "🔴"
        elif risk["risk_score"] >= 1.0:
            risk_icon = "🟡"
        else:
            risk_icon = "🟢"
        
        report.append(f"{i:2d}. {risk_icon} {risk['name']}")
        report.append(f"     📂 类别: {risk['category']}")
        report.append(f"     📊 概率: {risk['probability']:.0%}")
        report.append(f"     💥 影响: {risk['impact']}")
        report.append(f"     ⚠️  风险值: {risk['risk_score']:.2f}")
        report.append(f"     📝 描述: {risk['description']}")
        
        # 添加缓解策略
        if risk['name'] in strategies:
            report.append(f"     🛡️  缓解策略:")
            for strategy in strategies[risk['name']]:
                report.append(f"        • {strategy}")
        report.append("")
    
    # 风险管理建议
    report.append("💡 风险管理建议:")
    report.append("-" * 40)
    
    if high_risks:
        report.append("🔴 高优先级行动:")
        for risk in high_risks[:3]:  # 只显示前3个最高风险
            report.append(f"   • 立即制定 '{risk['name']}' 的应对计划")
    
    report.append("📋 常规风险管理措施:")
    report.append("   • 建立每周风险评估例会")
    report.append("   • 设置风险预警指标和监控机制")
    report.append("   • 准备应急响应团队和联系方式")
    report.append("   • 定期更新风险评估和缓解策略")
    
    return "\n".join(report)

# 技能主函数
def execute(project_type="e-commerce", team_size=12, budget=200, duration_months=6):
    """
    执行风险评估技能
    
    Args:
        project_type (str): 项目类型
        team_size (int): 团队规模
        budget (int): 项目预算（万元）
        duration_months (int): 项目周期（月）
    
    Returns:
        dict: 风险评估结果
    """
    try:
        # 评估项目风险
        risks = assess_project_risks(project_type, team_size, budget * 10000, duration_months)
        
        # 生成缓解策略
        strategies = generate_risk_mitigation_strategies(risks)
        
        # 项目信息
        project_info = {
            "type": project_type,
            "team_size": team_size,
            "budget": budget,
            "duration": duration_months
        }
        
        # 生成报告文本
        report_text = generate_risk_report_text(risks, strategies, project_info)
        
        return {
            "success": True,
            "risks": risks,
            "strategies": strategies,
            "report_text": report_text,
            "summary": {
                "total_risks": len(risks),
                "high_risks": len([r for r in risks if r["risk_score"] >= 2.0]),
                "top_risk": risks[0]["name"] if risks else None
            },
            "message": f"成功评估了 {len(risks)} 项风险"
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "message": "风险评估失败"
        }

if __name__ == "__main__":
    # 测试代码
    result = execute()
    if result["success"]:
        print(result["report_text"])
    else:
        print(f"错误: {result['error']}")
