from dotenv import load_dotenv
from pathlib import Path
import os

# 加载 .env
env_path = Path(__file__).parent / ".env"
load_dotenv(env_path)

# 打印结果
key = os.getenv("DEEPSEEK_API_KEY")
print(f".env 路径: {env_path}")
print(f".env 是否存在: {env_path.exists()}")
print(f"DEEPSEEK_API_KEY: {key[:20]}..." if key else "未找到")