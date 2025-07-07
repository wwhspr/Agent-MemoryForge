# 可以创建一个单独的 Python 脚本来执行
from modelscope import snapshot_download

# 定义您想存放所有AI模型的根目录
model_root_path = "/path/to/your/ai-models" 

# 下载模型，它会自动创建 qwen3-embedding-0.6b 子目录
model_dir = snapshot_download('xiaowangge/qwen3-embedding-0.6b', cache_dir=model_root_path)

print(f"模型已下载到: {model_dir}")
