
def get_skill_metadata():
    """获取技能元数据"""
    return {
        "name": "format_document",
        "description": "Execute format document related tasks",
        "parameters": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "需要格式化的文档内容"
                },
                "format_type": {
                    "type": "string",
                    "description": "格式化类型，可选：markdown, plain",
                    "default": "markdown"
                }
            },
            "required": ["text"]
        }
    }

def execute(text, format_type='markdown'):
    if format_type == 'markdown': return f'# Document\n\n{text}'
    else: return text.upper()