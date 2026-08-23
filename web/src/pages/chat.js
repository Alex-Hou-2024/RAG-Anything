import { streamQuery } from "../api/client.js";
import { createCitations } from "../components/citations.js";
import { createNotice } from "../components/layout.js";

const MODES = [
  ["hybrid", "混合检索"],
  ["local", "局部检索"],
  ["global", "全局检索"],
  ["naive", "基础检索"],
  ["mix", "混合模式"],
];

export function createChatPage() {
  const page = document.createElement("section");
  page.className = "page page--chat";
  page.innerHTML = `
    <div class="page-heading"><div><p class="eyebrow">检索问答</p><h1>对话问答</h1><p>选择检索模式并提出问题，回答将以流式方式显示。</p></div></div>
    <section class="chat-panel" aria-label="问答记录"><div class="message-list" aria-live="polite"></div></section>
    <form class="chat-form">
      <label>检索模式<select name="mode"></select></label>
      <label>问题<textarea name="query" rows="4" required maxlength="20000" placeholder="例如：请概括已上传文档中的关键结论。"></textarea></label>
      <div class="chat-error"></div><button class="button button--primary" type="submit">发送问题</button>
    </form>`;

  const selector = page.querySelector("select[name=mode]");
  for (const [value, label] of MODES) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = label;
    selector.append(option);
  }
  const form = page.querySelector(".chat-form");
  const input = page.querySelector("textarea[name=query]");
  const messages = page.querySelector(".message-list");
  const errorBox = page.querySelector(".chat-error");
  const submit = form.querySelector("button[type=submit]");

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const query = input.value.trim();
    if (!query) return;
    errorBox.replaceChildren();
    appendMessage(messages, "question", query);
    const answer = appendMessage(messages, "answer", "正在检索并生成回答…");
    let answerText = "";
    let citations = [];
    submit.disabled = true;
    input.disabled = true;
    try {
      await streamQuery(
        { query, mode: selector.value },
        {
          delta: (data) => {
            answerText += data.text || "";
            answer.textContent = answerText || "正在生成回答…";
          },
          citations: (data) => { citations = Array.isArray(data.citations) ? data.citations : []; },
          done: () => {
            if (!answerText) answer.textContent = "未收到回答内容。";
          },
          error: (data) => { throw new Error(data.message || "回答生成失败"); },
        },
      );
      answer.after(createCitations(citations));
    } catch (error) {
      answer.textContent = "本次回答未能完成。";
      errorBox.replaceChildren(createNotice(`问答失败：${error.message}`));
    } finally {
      submit.disabled = false;
      input.disabled = false;
      input.value = "";
      input.focus();
    }
  });

  return { element: page, dispose: () => {} };
}

function appendMessage(container, kind, text) {
  const article = document.createElement("article");
  article.className = `message message--${kind}`;
  const label = document.createElement("strong");
  label.textContent = kind === "question" ? "你" : "回答";
  const content = document.createElement("p");
  content.textContent = text;
  article.append(label, content);
  container.append(article);
  container.scrollTop = container.scrollHeight;
  return content;
}
