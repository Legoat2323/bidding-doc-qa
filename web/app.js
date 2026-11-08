/* 文档问答前端：原生 JS，无构建链。
   渲染用自己的迷你 Markdown（支持标题 / 有序无序列表 / 表格 / 加粗 / 行内代码），
   不依赖外部 CDN，离线也能用。 */

const $ = (id) => document.getElementById(id);
const BID_DOC = "招标文件正文22.pdf";

let state = { doc: null, template: null, templates: [] };

/* ---------------- 迷你 Markdown ---------------- */
function inline(text) {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/`([^`]+)`/g, "<code>$1</code>");
}

function renderMarkdown(md) {
  const lines = md.split("\n");
  const out = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];
    const s = line.trim();

    if (!s) { i++; continue; }

    // 表格
    if (s.startsWith("|")) {
      const block = [];
      while (i < lines.length && lines[i].trim().startsWith("|")) {
        block.push(lines[i].trim());
        i++;
      }
      const rows = block
        .map((r) => r.split("|").slice(1, -1).map((c) => c.trim()))
        .filter((r) => !r.every((c) => /^[-: ]*$/.test(c)));
      if (rows.length) {
        out.push("<table>");
        rows.forEach((r, idx) => {
          const tag = idx === 0 ? "th" : "td";
          out.push("<tr>" + r.map((c) => `<${tag}>${inline(c)}</${tag}>`).join("") + "</tr>");
        });
        out.push("</table>");
      }
      continue;
    }

    // 标题
    if (s.startsWith("### ")) { out.push(`<h3>${inline(s.slice(4))}</h3>`); i++; continue; }
    if (s.startsWith("## ")) { out.push(`<h3>${inline(s.slice(3))}</h3>`); i++; continue; }

    // 列表
    if (/^(\d+)\.\s/.test(s) || /^[-*]\s/.test(s)) {
      const ordered = /^(\d+)\.\s/.test(s);
      const items = [];
      while (i < lines.length) {
        const cur = lines[i].trim();
        const m = cur.match(/^(\d+)\.\s+(.*)$/);
        const b = cur.match(/^[-*]\s+(.*)$/);
        if (m) { items.push(m[2]); i++; }
        else if (b) { items.push(b[1]); i++; }
        else if (cur && !/^(\d+)\.\s/.test(cur) && !/^[-*]\s/.test(cur) && !cur.startsWith("|")) {
          // 续行，接到上一条
          if (items.length) items[items.length - 1] += " " + cur;
          i++;
        } else break;
      }
      const tag = ordered ? "ol" : "ul";
      out.push(`<${tag}>` + items.map((t) => `<li>${inline(t)}</li>`).join("") + `</${tag}>`);
      continue;
    }

    // 分隔线
    if (/^---+$/.test(s)) { i++; continue; }

    // 普通段落
    const buf = [s];
    i++;
    while (i < lines.length) {
      const nxt = lines[i].trim();
      if (!nxt || nxt.startsWith("|") || nxt.startsWith("#") || /^(\d+)\.\s/.test(nxt) || /^[-*]\s/.test(nxt)) break;
      buf.push(nxt);
      i++;
    }
    out.push(`<p>${inline(buf.join(" "))}</p>`);
  }

  return out.join("\n");
}

/* ---------------- 渲染 ---------------- */
function setStatus(text, warn = false) {
  const el = $("statusBadge");
  el.textContent = text;
  el.className = "badge" + (warn ? " warn" : "");
}

function renderFactCheck(fc) {
  const box = $("factcheck");
  if (!fc || fc.checked === 0) { box.innerHTML = ""; return; }
  if (fc.missing.length === 0) {
    box.innerHTML = `<div class="factcheck ok">✅ 事实校验：答案里的 ${fc.checked} 个数值，都能在原文片段中找到。</div>`;
  } else {
    const items = fc.missing.map((m) => `<code>${m}</code>`).join("、");
    box.innerHTML =
      `<div class="factcheck warn">⚠️ 事实校验：${fc.checked} 个数值中有 ${fc.missing.length} 个` +
      `未在原文找到：${items}<br/>这几个数字可能是模型补的，用之前请回原文核对。</div>`;
  }
}

function renderSources(sources) {
  const box = $("sourcesBox");
  if (!sources || !sources.length) { box.style.display = "none"; return; }
  box.style.display = "block";
  $("sources").innerHTML = sources
    .map(
      (s) =>
        `<div class="source-item"><span class="ref">[${s.ref}]</span>${s.text
          .replace(/&/g, "&amp;")
          .replace(/</g, "&lt;")
          .slice(0, 320)}</div>`
    )
    .join("");
}

/* ---------------- 请求 ---------------- */
async function ask() {
  const doc = $("doc").value;
  const question = $("question").value.trim();
  const useTemplate = state.template && !question && doc === BID_DOC;

  if (!useTemplate && !question) {
    $("answer").innerHTML = '<span class="empty">请输入问题。</span>';
    return;
  }

  const body = { question: question || "（查询模板问题）", doc };
  if (useTemplate) body.template = state.template;

  $("askBtn").disabled = true;
  setStatus("查询中…");
  $("answer").innerHTML = '<span class="empty"><span class="spinner"></span>正在检索并生成…</span>';
  $("factcheck").innerHTML = "";

  const t0 = Date.now();
  try {
    const res = await fetch("/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) {
      $("answer").innerHTML = `<span class="empty">请求失败：${data.detail || res.status}</span>`;
      setStatus("失败", true);
      return;
    }
    $("answer").innerHTML = renderMarkdown(data.answer || "");
    renderFactCheck(data.fact_check);
    renderSources(data.sources);
    setStatus(`${((Date.now() - t0) / 1000).toFixed(1)}s · ${data.model}`);
  } catch (e) {
    $("answer").innerHTML = `<span class="empty">网络错误：${e}</span>`;
    setStatus("失败", true);
  } finally {
    $("askBtn").disabled = false;
  }
}

/* ---------------- 初始化 ---------------- */
async function loadDocs() {
  const res = await fetch("/documents");
  const data = await res.json();
  const sel = $("doc");
  sel.innerHTML = data.documents.map((d) => `<option>${d}</option>`).join("");
  sel.value = data.default;
  state.doc = sel.value;
  onDocChange();
}

async function loadTemplates() {
  const res = await fetch("/templates");
  const data = await res.json();
  state.templates = data.templates;
  renderPresets();
}

function renderPresets() {
  const box = $("presets");
  const enabled = $("doc").value === BID_DOC;
  if (!enabled) {
    box.innerHTML = '<span class="empty">当前文档没有预设问题，请直接提问。</span>';
    state.template = null;
    return;
  }
  box.innerHTML = state.templates
    .map((t) => `<button class="preset" data-t="${t}">${t}</button>`)
    .join("");
  box.querySelectorAll(".preset").forEach((b) => {
    b.onclick = () => {
      state.template = b.dataset.t;
      box.querySelectorAll(".preset").forEach((x) => x.classList.remove("active"));
      b.classList.add("active");
      $("question").value = "";
      ask();
    };
  });
}

function onDocChange() {
  state.doc = $("doc").value;
  $("question").value = "";
  renderPresets();
  $("answer").innerHTML = '<span class="empty">选一个预设问题，或在左侧输入你的问题。</span>';
  $("factcheck").innerHTML = "";
  $("sourcesBox").style.display = "none";
  $("hint").textContent =
    state.doc === BID_DOC
      ? "预设问题是按这份文档的用词写的检索式，命中率比口语提问高。换其他文档时预设会失效，走通用 RAG。"
      : `已切换到「${state.doc}」，这份文档没有预设问题，请在下面直接提问。`;
}

async function upload() {
  const f = $("file").files[0];
  if (!f) { $("uploadStatus").textContent = "先选择文件"; return; }
  $("uploadBtn").disabled = true;
  $("uploadStatus").textContent = "上传并建索引中（大文件要等一会儿）…";
  const fd = new FormData();
  fd.append("file", f);
  try {
    const res = await fetch("/upload", { method: "POST", body: fd });
    const data = await res.json();
    if (!res.ok) { $("uploadStatus").textContent = "失败：" + (data.detail || res.status); return; }
    $("uploadStatus").textContent = `已添加：${data.uploaded}`;
    const sel = $("doc");
    sel.innerHTML = data.documents.map((d) => `<option>${d}</option>`).join("");
    sel.value = data.uploaded;
    onDocChange();
  } catch (e) {
    $("uploadStatus").textContent = "网络错误：" + e;
  } finally {
    $("uploadBtn").disabled = false;
  }
}

$("askBtn").onclick = ask;
$("doc").onchange = onDocChange;
$("question").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) ask();
});
$("uploadBtn").onclick = upload;

loadDocs();
loadTemplates();
