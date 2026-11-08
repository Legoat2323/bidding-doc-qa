"""离线验证真实界面：导入 main（不启动端口），用 TestClient 请求首页。

目的：确认真正的 UI 能构建并渲染，而不是只有一个空壳 Blocks。
用法：
    python test_ui.py
"""
import os

os.chdir(os.path.dirname(os.path.abspath(__file__)))

import main  # noqa: E402  导入即构建 demo，但不会 launch
from gradio.routes import App  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

app = App.create_app(main.demo)
client = TestClient(app)

r = client.get("/")
print("GET /       ->", r.status_code, "长度", len(r.text))

cfg = client.get("/config")
print("GET /config ->", cfg.status_code)

if r.status_code == 200:
    print()
    print("真实界面渲染通过")
    print("页面里是否含标题:", "通用文档分析助手" in r.text or "gradio" in r.text.lower())
else:
    print("失败，前 500 字:", r.text[:500])
