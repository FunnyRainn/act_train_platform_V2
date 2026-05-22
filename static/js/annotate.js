let state = {
  bootstrap: null,
  frameSetId: "",
  frames: [],
  frameIndex: 0,
  boxes: [],
  drawing: null,
  selectedIndex: -1,
  drag: null,
  saveTimer: null,
  pendingSavePayload: null,
  saving: Promise.resolve(),
  imageLoadToken: 0,
};

const canvas = $("#bbox-canvas");
const ctx = canvas.getContext("2d");
const image = $("#frame-image");

async function initAnnotator() {
  state.bootstrap = await loadBootstrap();
  fillSelect($("#frame-set-select"), state.bootstrap.frame_sets, item => item.id, item => `${item.name} (${item.frame_count}帧)`, "选择帧集");
  fillSelect($("#label-select"), state.bootstrap.labels.filter(item => item.enabled), item => item.code, item => `${item.code} ${item.name}`, "选择标签");
  updatePrelabelStatus("预标注空闲");
}

async function loadFrameSet(frameSetId) {
  if (!frameSetId) return;
  await flushPendingSave();
  state.frameSetId = frameSetId;
  state.frames = await apiGet(`/api/frame-sets/${frameSetId}/frames`);
  state.frameIndex = 0;
  updatePrelabelStatus("预标注空闲");
  await showFrame();
}

function currentFrame() {
  return state.frames[state.frameIndex];
}

function currentFrameSet() {
  return state.bootstrap.frame_sets.find(item => item.id === state.frameSetId);
}

function boxesSnapshot() {
  return state.boxes.map(box => ({ ...box }));
}

function currentSavePayload() {
  const frame = currentFrame();
  const frameSet = currentFrameSet();
  if (!state.frameSetId || !frame || !frameSet) return null;
  return {
    project_id: frameSet.project_id,
    frame_set_id: state.frameSetId,
    frame_id: frame.id,
    annotations: boxesSnapshot(),
  };
}

function updateFrameInfo() {
  const frame = currentFrame();
  if (!frame) {
    $("#frame-info").textContent = "未选择帧";
    return;
  }
  const total = state.boxes.length;
  const prelabels = state.boxes.filter(box => box.source === "prelabel").length;
  $("#frame-info").textContent = `${state.frameIndex + 1}/${state.frames.length} | 原始帧号 ${frame.frame_index} | 当前帧框数 ${total} | 预标注 ${prelabels}`;
}

async function showFrame() {
  await flushPendingSave();
  if (!state.frames.length) {
    $("#frame-info").textContent = "帧集为空";
    return;
  }
  const frame = currentFrame();
  const token = ++state.imageLoadToken;
  image.onload = async () => {
    if (token !== state.imageLoadToken || frame.id !== currentFrame()?.id) return;
    image.style.display = "block";
    fitCanvas();
    await loadBoxes(frame.id, token);
    draw();
  };
  image.src = `/api/frames/${frame.id}/image?ts=${Date.now()}`;
  updateFrameInfo();
}

function fitCanvas() {
  const rect = image.getBoundingClientRect();
  canvas.width = Math.max(1, Math.round(rect.width));
  canvas.height = Math.max(1, Math.round(rect.height));
  canvas.style.left = `${image.offsetLeft}px`;
  canvas.style.top = `${image.offsetTop}px`;
  canvas.style.width = `${rect.width}px`;
  canvas.style.height = `${rect.height}px`;
}

async function loadBoxes(frameId = null, token = state.imageLoadToken) {
  await flushPendingSave();
  const frame = currentFrame();
  if (!frame) return;
  const expectedFrameId = frameId || frame.id;
  const boxes = await apiGet(`/api/frame-sets/${state.frameSetId}/annotations?frame_id=${expectedFrameId}`);
  if (token !== state.imageLoadToken || expectedFrameId !== currentFrame()?.id) return;
  state.boxes = boxes;
  state.selectedIndex = -1;
  renderBoxList();
  updateFrameInfo();
}

function confidenceText(box) {
  const value = Number(box.confidence);
  return Number.isFinite(value) ? value.toFixed(2) : "";
}

function renderBoxList() {
  $("#box-list").innerHTML = state.boxes.map((box, idx) => {
    const confidence = confidenceText(box);
    return `
      <div class="box-item ${idx === state.selectedIndex ? "selected" : ""}">
        <strong>${esc(box.label_code)}</strong>
        ${box.track_id ? `<span>跟踪对象 ${esc(box.track_id.slice(-6))}</span>` : ""}
        <div>
          来源: ${sourceText(box.source)}
          ${confidence ? ` | 置信度: ${confidence}` : ""}
          | ${box.is_keyframe ? "关键帧" : "普通帧"}
          | ${box.confirmed ? "已确认" : "待确认"}
        </div>
        <button data-select="${idx}">选中</button>
        ${box.source === "prelabel" && !box.confirmed ? `<button data-confirm="${idx}">确认该框</button>` : ""}
        <button data-delete="${idx}">删除</button>
      </div>
    `;
  }).join("");
  $$('[data-select]').forEach(btn => btn.onclick = () => selectBox(Number(btn.dataset.select)));
  $$('[data-confirm]').forEach(btn => btn.onclick = () => {
    state.boxes[Number(btn.dataset.confirm)].confirmed = true;
    scheduleSave();
    renderBoxList();
    draw();
  });
  $$('[data-delete]').forEach(btn => btn.onclick = () => {
    state.boxes.splice(Number(btn.dataset.delete), 1);
    state.selectedIndex = -1;
    scheduleSave();
    renderBoxList();
    draw();
  });
  updateFrameInfo();
}

function sourceText(source) {
  return { manual: "人工", interpolated: "中间帧", prelabel: "预标注" }[source] || source || "人工";
}

function selectBox(idx) {
  state.selectedIndex = idx;
  const box = state.boxes[idx];
  if (box) {
    $("#label-select").value = box.label_code;
    $("#track-id").value = box.track_id || "";
    $("#is-keyframe").checked = Boolean(box.is_keyframe);
  }
  renderBoxList();
  draw();
}

function toPixelBox(box) {
  return {
    x: box.x * canvas.width,
    y: box.y * canvas.height,
    w: box.w * canvas.width,
    h: box.h * canvas.height,
  };
}

function toNormBox(rect) {
  return clampBox({
    x: rect.x / canvas.width,
    y: rect.y / canvas.height,
    w: rect.w / canvas.width,
    h: rect.h / canvas.height,
  });
}

function clampBox(box) {
  let x = Math.max(0, Math.min(1, Number(box.x) || 0));
  let y = Math.max(0, Math.min(1, Number(box.y) || 0));
  let w = Math.max(0.001, Math.min(1, Number(box.w) || 0.001));
  let h = Math.max(0.001, Math.min(1, Number(box.h) || 0.001));
  if (x + w > 1) w = 1 - x;
  if (y + h > 1) h = 1 - y;
  return { ...box, x, y, w, h };
}

function pointer(event) {
  const box = canvas.getBoundingClientRect();
  return {
    x: event.clientX - box.left,
    y: event.clientY - box.top,
  };
}

function hitTest(point) {
  for (let i = state.boxes.length - 1; i >= 0; i--) {
    const box = toPixelBox(state.boxes[i]);
    const inside = point.x >= box.x && point.x <= box.x + box.w && point.y >= box.y && point.y <= box.y + box.h;
    if (!inside) continue;
    const edge = 8;
    let mode = "move";
    if (Math.abs(point.x - box.x) < edge) mode = "w";
    if (Math.abs(point.x - (box.x + box.w)) < edge) mode = "e";
    if (Math.abs(point.y - box.y) < edge) mode += "n";
    if (Math.abs(point.y - (box.y + box.h)) < edge) mode += "s";
    return { index: i, mode };
  }
  return null;
}

canvas.addEventListener("mousedown", event => {
  if (!state.frameSetId || !currentFrame()) return;
  const p = pointer(event);
  const hit = hitTest(p);
  if (hit) {
    selectBox(hit.index);
    state.drag = { ...hit, start: p, original: { ...state.boxes[hit.index] } };
    return;
  }
  state.selectedIndex = -1;
  state.drawing = { x: p.x, y: p.y, w: 0, h: 0 };
  renderBoxList();
});

canvas.addEventListener("mousemove", event => {
  const p = pointer(event);
  if (state.drag) {
    dragSelected(p);
    return;
  }
  if (!state.drawing) return;
  state.drawing.w = p.x - state.drawing.x;
  state.drawing.h = p.y - state.drawing.y;
  draw();
});

window.addEventListener("mouseup", () => {
  if (state.drag) {
    state.drag = null;
    scheduleSave();
    return;
  }
  if (!state.drawing) return;
  const rect = normalizePixelRect(state.drawing);
  state.drawing = null;
  const box = toNormBox(rect);
  if (box.w < 0.005 || box.h < 0.005) {
    showToast("框太小，已忽略", "error");
    draw();
    return;
  }
  state.boxes.push({
    id: null,
    label_code: $("#label-select").value,
    track_id: $("#track-id").value.trim() || null,
    ...box,
    source: "manual",
    is_keyframe: $("#is-keyframe").checked,
    confirmed: true,
    confidence: null,
  });
  state.selectedIndex = state.boxes.length - 1;
  scheduleSave();
  renderBoxList();
  draw();
});

function normalizePixelRect(rect) {
  const x = Math.min(rect.x, rect.x + rect.w);
  const y = Math.min(rect.y, rect.y + rect.h);
  return { x, y, w: Math.abs(rect.w), h: Math.abs(rect.h) };
}

function dragSelected(p) {
  const d = state.drag;
  const box = { ...d.original };
  const dx = (p.x - d.start.x) / canvas.width;
  const dy = (p.y - d.start.y) / canvas.height;
  if (d.mode === "move") {
    box.x += dx;
    box.y += dy;
  } else {
    if (d.mode.includes("w")) { box.x += dx; box.w -= dx; }
    if (d.mode.includes("e")) { box.w += dx; }
    if (d.mode.includes("n")) { box.y += dy; box.h -= dy; }
    if (d.mode.includes("s")) { box.h += dy; }
  }
  state.boxes[d.index] = clampBox(box);
  draw();
}

function draw() {
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  state.boxes.forEach((box, idx) => {
    const p = toPixelBox(box);
    const color = box.source === "prelabel" && !box.confirmed ? "#f5a623" : box.source === "interpolated" ? "#8fb4ff" : box.is_keyframe ? "#1fbf75" : "#2f76ff";
    const confidence = confidenceText(box);
    const label = `${box.label_code} ${sourceText(box.source)}${confidence ? ` ${confidence}` : ""}`;
    ctx.strokeStyle = idx === state.selectedIndex ? "#ffffff" : color;
    ctx.lineWidth = idx === state.selectedIndex ? 3 : 2;
    ctx.strokeRect(p.x, p.y, p.w, p.h);
    ctx.font = "13px Microsoft YaHei";
    const labelWidth = Math.min(220, ctx.measureText(label).width + 16);
    ctx.fillStyle = "rgba(15,23,42,.78)";
    ctx.fillRect(p.x, Math.max(0, p.y - 22), labelWidth, 22);
    ctx.fillStyle = "#fff";
    ctx.fillText(label, p.x + 6, Math.max(14, p.y - 7));
  });
  if (state.drawing) {
    const rect = normalizePixelRect(state.drawing);
    ctx.strokeStyle = "#ffcc00";
    ctx.lineWidth = 2;
    ctx.strokeRect(rect.x, rect.y, rect.w, rect.h);
  }
}

function scheduleSave() {
  const payload = currentSavePayload();
  if (!payload) return;
  state.pendingSavePayload = payload;
  $("#save-status").textContent = "保存中...";
  clearTimeout(state.saveTimer);
  state.saveTimer = setTimeout(() => saveFramePayload(payload), 450);
}

async function flushPendingSave() {
  if (!state.saveTimer) {
    await state.saving;
    return;
  }
  clearTimeout(state.saveTimer);
  state.saveTimer = null;
  const payload = state.pendingSavePayload || currentSavePayload();
  state.pendingSavePayload = null;
  if (payload) await saveFramePayload(payload);
  await state.saving;
}

async function saveFramePayload(payload) {
  clearTimeout(state.saveTimer);
  state.saveTimer = null;
  state.pendingSavePayload = null;
  state.saving = state.saving.then(async () => {
    try {
      await apiPost("/api/annotations/frame", payload);
      $("#save-status").textContent = "已保存";
    } catch (error) {
      $("#save-status").textContent = "保存失败";
      showToast(error.message, "error");
    }
  });
  return state.saving;
}

async function saveCurrentFrame() {
  const payload = currentSavePayload();
  if (!payload) return;
  await saveFramePayload(payload);
}

async function goFrame(delta) {
  if (!state.frames.length) return;
  const nextIndex = state.frameIndex + delta;
  if (nextIndex < 0 || nextIndex >= state.frames.length) return;
  await flushPendingSave();
  state.frameIndex = nextIndex;
  await showFrame();
}

function clearCurrentFrameBoxes() {
  if (!state.frameSetId || !currentFrame()) return;
  state.boxes = [];
  state.selectedIndex = -1;
  scheduleSave();
  renderBoxList();
  draw();
}

function updatePrelabelStatus(message, type = "") {
  const el = $("#prelabel-status");
  if (!el) return;
  el.textContent = message;
  el.dataset.status = type;
}

$("#frame-set-select").addEventListener("change", event => loadFrameSet(event.target.value));
$("#label-select").addEventListener("change", () => {
  if (state.selectedIndex >= 0) {
    state.boxes[state.selectedIndex].label_code = $("#label-select").value;
    scheduleSave();
    renderBoxList();
    draw();
  }
});
$("#is-keyframe").addEventListener("change", () => {
  if (state.selectedIndex >= 0) {
    state.boxes[state.selectedIndex].is_keyframe = $("#is-keyframe").checked;
    state.boxes[state.selectedIndex].source = "manual";
    state.boxes[state.selectedIndex].confirmed = true;
    scheduleSave();
    renderBoxList();
    draw();
  }
});

$("#new-track-btn").addEventListener("click", async () => {
  try {
    const frameSet = currentFrameSet();
    if (!frameSet) throw new Error("请先选择帧集");
    const track = await apiPost("/api/tracks", {
      project_id: frameSet.project_id,
      frame_set_id: state.frameSetId,
      label_code: $("#label-select").value,
      track_id: $("#track-id").value.trim() || null,
    });
    $("#track-id").value = track.id;
    if (state.selectedIndex >= 0) {
      state.boxes[state.selectedIndex].track_id = track.id;
      state.boxes[state.selectedIndex].is_keyframe = true;
      state.boxes[state.selectedIndex].confirmed = true;
      $("#is-keyframe").checked = true;
      scheduleSave();
    }
    showToast("跟踪对象已准备");
    renderBoxList();
    draw();
  } catch (error) {
    showToast(error.message, "error");
  }
});

$("#save-frame-btn").addEventListener("click", saveCurrentFrame);
$("#interpolate-btn").addEventListener("click", async () => {
  try {
    await flushPendingSave();
    const trackId = $("#track-id").value;
    if (!trackId) throw new Error("请先新建或填写跟踪对象");
    const result = await apiPost(`/api/tracks/${trackId}/interpolate`, { frame_set_id: state.frameSetId });
    showToast(`中间帧生成完成，共 ${result.generated} 个框`);
    await loadBoxes();
    draw();
  } catch (error) {
    showToast(error.message, "error");
  }
});

$("#prelabel-btn").addEventListener("click", async () => {
  const button = $("#prelabel-btn");
  try {
    await flushPendingSave();
    const modelPath = $("#prelabel-model").value.trim();
    if (!state.frameSetId) throw new Error("请先选择帧集");
    if (!modelPath) throw new Error("请填写旧模型路径");
    const conf = Number($("#prelabel-conf").value || 0.25);
    if (!Number.isFinite(conf) || conf < 0.05 || conf > 0.95) throw new Error("预标注置信度需要在 0.05 到 0.95 之间");
    const startText = new Date().toLocaleTimeString();
    button.disabled = true;
    button.textContent = "预标注运行中...";
    updatePrelabelStatus(`预标注运行中，开始时间 ${startText}`, "running");
    await new Promise(requestAnimationFrame);
    const result = await apiPost("/api/prelabel", { frame_set_id: state.frameSetId, model_path: modelPath, conf });
    await loadBoxes();
    const currentPrelabels = state.boxes.filter(box => box.source === "prelabel").length;
    updatePrelabelStatus(`本次新增 ${result.created} 个；当前帧集共 ${result.total ?? result.created} 个预标注框，分布在 ${result.frames ?? "-"} 帧；当前帧 ${currentPrelabels} 个，待确认 ${result.pending ?? "-"} 个`, "done");
    showToast(`当前帧集共 ${result.total ?? result.created} 个预标注框`);
    draw();
  } catch (error) {
    updatePrelabelStatus(`预标注失败：${error.message}`, "error");
    showToast(error.message, "error");
  } finally {
    button.disabled = false;
    button.textContent = "运行预标注";
  }
});

$("#confirm-prelabels-btn")?.addEventListener("click", async () => {
  if (!state.frameSetId) return showToast("请先选择帧集", "warn");
  try {
    if (!confirm("将确认当前帧集全部未确认预标注框，确认后会参与训练数据集导出。确定继续吗？")) return;
    const result = await apiPost("/api/prelabel/confirm-all", { frame_set_id: state.frameSetId });
    showToast(`已确认 ${result.confirmed || 0} 个预标注框`);
    updatePrelabelStatus(`已确认当前帧集 ${result.confirmed || 0} 个预标注框`, "done");
    await loadBoxes();
    draw();
  } catch (error) {
    showToast(error.message, "error");
  }
});

$("#clear-prelabels-btn")?.addEventListener("click", async () => {
  try {
    await flushPendingSave();
    if (!state.frameSetId) throw new Error("请先选择帧集");
    if (!confirm("将清空当前帧集全部未确认的预标注框，不会删除人工框和已确认框。确定继续吗？")) return;
    const result = await apiPost("/api/prelabel/clear", { frame_set_id: state.frameSetId });
    updatePrelabelStatus(`已清空 ${result.deleted} 个未确认预标注框`, "done");
    showToast(`已清空 ${result.deleted} 个未确认预标注框`);
    await loadBoxes();
    draw();
  } catch (error) {
    showToast(error.message, "error");
  }
});

$("#clear-boxes-btn")?.addEventListener("click", clearCurrentFrameBoxes);
$("#prev-frame").addEventListener("click", () => goFrame(-1));
$("#next-frame").addEventListener("click", () => goFrame(1));

function isTypingTarget(target) {
  const tagName = target?.tagName?.toLowerCase();
  return target?.isContentEditable || ["input", "textarea"].includes(tagName);
}

document.addEventListener("keydown", event => {
  if (isTypingTarget(event.target)) return;
  if (event.ctrlKey && !event.altKey && !event.metaKey && (event.code === "KeyO" || event.key.toLowerCase() === "o")) {
    event.preventDefault();
    clearCurrentFrameBoxes();
    return;
  }
  if (event.ctrlKey || event.altKey || event.metaKey) return;
  const key = event.key.toLowerCase();
  if (event.code === "KeyA" || key === "a") {
    event.preventDefault();
    goFrame(-1);
  }
  if (event.code === "KeyD" || key === "d") {
    event.preventDefault();
    goFrame(1);
  }
});

initAnnotator().catch(error => showToast(error.message, "error"));
