"""离线验证 Gradio 页面能否正常渲染（不开端口、不联网）。

用法：
    python test_render.py
"""
import gradio as gr
from gradio.routes import App
from starlette.testclient import TestClient

with gr.Blocks() as demo:
    gr.HTML("<h1 align='center'>render test</h1>")
    gr.Chatbot(show_label=False)
    gr.Textbox()
    gr.File(label="upload")

app = App.create_app(demo)
client = TestClient(app)

r = client.get("/")
print("GET / ->", r.status_code, "长度", len(r.text))
print("包含 gradio 标记:", "gradio" in r.text.lower())

r2 = client.get("/config")
print("GET /config ->", r2.status_code)

if r.status_code == 200:
    print("渲染测试通过")
else:
    print("渲染失败，前 500 字:", r.text[:500])
