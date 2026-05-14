const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

function showToast(message, type = "info") {
  const toast = $("#toast");
  toast.textContent = message;
  toast.className = `toast show ${type}`;
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => toast.className = "toast", 2800);
}

async function apiGet(url) {
  const res = await fetch(url);
  return parseApiResponse(res);
}

async function apiPost(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return parseApiResponse(res);
}

async function parseApiResponse(res) {
  const contentType = res.headers.get("content-type") || "";
  const data = contentType.includes("application/json") ? await res.json() : await res.text();
  if (!res.ok) {
    const message = data.detail || data.message || data || `请求失败: ${res.status}`;
    throw new Error(message);
  }
  return data;
}

async function loadBootstrap() {
  return apiGet("/api/bootstrap");
}

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, ch => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;",
  }[ch]));
}

function formToObject(form) {
  const data = new FormData(form);
  const obj = {};
  for (const [key, value] of data.entries()) {
    if (obj[key] !== undefined) {
      obj[key] = Array.isArray(obj[key]) ? [...obj[key], value] : [obj[key], value];
    } else {
      obj[key] = value;
    }
  }
  $$("select[multiple]", form).forEach(select => {
    obj[select.name] = Array.from(select.selectedOptions).map(option => option.value);
  });
  $$("input[type=checkbox]", form).forEach(input => {
    obj[input.name] = input.checked;
  });
  return obj;
}

function fillSelect(select, items, getValue, getLabel, placeholder = "请选择") {
  select.innerHTML = `<option value="">${placeholder}</option>` + items.map(item => (
    `<option value="${esc(getValue(item))}">${esc(getLabel(item))}</option>`
  )).join("");
}

function fillMultiSelect(select, items, getValue, getLabel) {
  select.innerHTML = items.map(item => (
    `<option value="${esc(getValue(item))}">${esc(getLabel(item))}</option>`
  )).join("");
}

function rowHtml(title, meta, action = "") {
  return `<div class="row"><div><div class="row-title">${title}</div><div class="row-meta">${meta}</div></div><div>${action}</div></div>`;
}
