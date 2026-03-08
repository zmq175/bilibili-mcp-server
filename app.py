"""ModelScope MCP 云端部署入口。

ModelScope 会直接运行此文件。通过环境变量控制行为：
  MCP_TRANSPORT  : sse | http | stdio（默认 sse，云端用 sse）
  MCP_HOST       : 监听地址（默认 0.0.0.0）
  MCP_PORT       : 监听端口（默认 7860，ModelScope Studio 默认端口）
  SILICONFLOW_API_KEY : 硅基流动 API Key，在 ModelScope 平台的「环境变量/Secret」中配置
"""

import sys
from pathlib import Path

# 将 src 目录加入 Python 路径，使 bilibili_mcp 包可被导入
sys.path.insert(0, str(Path(__file__).parent / "src"))

from bilibili_mcp.server import main  # noqa: E402

if __name__ == "__main__":
    main()
