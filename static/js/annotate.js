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
  saving: Promise.resolve(),
};

const canvas = $("#bbox-canvas");
const ctx = canvas.getContext("2d");
const image = $("#frame-image");

async function initAnnotator() {
  state.bootstrap = await loadBootstrap();
  fillSelect($("#frame-set-select"), state.bootstrap.frame_sets, item => item.id, item => `${item.name} (${item.frame_count}帧)`, "选择帧集");
  fillSelect($("#label-select"), state.bootstrap.labels.filter(x => x.enabled), item => item.code, item => `${item.code} ${item.name}`, "选择标签");
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
  $("#frame-info").textContent = `${state.frameIndex + 1}/${state.frames.length} | 原始帧号 ${frame.frame_index} | 当前帧框数 ${state.boxes.length}`;
}

async function showFrame() {
  await flushPendingSave();
  if (!state.frames.length) {
    $("#frame-info").textContent = "帧集为空";
    return;
  }
  const frame = currentFrame();
  image.onload = async () => {
    image.style.display = "block";
    fitCanvas();
    await loadBoxes();
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

async function loadBoxes() {
  await flushPendingSave();
  const frame = currentFrame();
  state.boxes = await apiGet(`/api/frame-sets/${state.frameSetId}/annotations?frame_id=${frame.id}`);
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
        ${box.source === "prelabel" && !box.confirmed ? `<button data-confirm="${idx}">确认</button>` : ""}
        <button data-delete="${idx}">删除</button>
      </div>
    `;
  }).join("");
  $$("[data-select]").forEach(btn => btn.onclick = () => selectBox(Number(btn.dataset.select)));
  $$("[data-confirm]").forEach(btn => btn.onclick = () => {
    state.boxes[Number(btn.dataset.confirm)].confirmed = true;
    scheduleSave();
    renderBoxList();
    draw();
  });
  $$("[data-delete]").forEach(btn => btn.onclick = () => {
    state.boxes.splice(Number(btn.dataset.delete), 1);
    state.selectedIndex = -1;
    scheduleSave();
    renderBoxList();
    draw();
  });
  updateFrameInfo();
}

function sourceText(source) {
  return { manual: "人工", interpolated: "中间帧", prelabel: "预标注" }[source] || source;
}

function selectBox(idx) {
  state.selectedIndex = idx;
  const box = state.boxes[idx];
  if (box) {
    $("#label-select").value = box.label_code;
    $("#track-id").value = box.track_id || "";
    $("#is-keyframe").checked = !!box.is_keyframe;
  }
  renderBoxList();
  draw();
}

function canvasPoint(event) {
  const rect = canvas.getBoundingClientRect();
  return {
    x: Math.max(0, Math.min(rect.width, event.clientX - rect.left)),
    y: Math.max(0, Math.min(rect.height, event.clientY - rect.top)),
  };
}

function toNormBox(pxBox) {
  const x = Math.min(pxBox.x1, pxBox.x2) / canvas.width;
  const y = Math.min(pxBox.y1, pxBox.y2) / canvas.height;
  const w = Math.abs(pxBox.x2 - pxBox.x1) / canvas.width;
  const h = Math.abs(pxBox.y2 - pxBox.y1) / canvas.height;
  return clampBox({ x, y, w, h });
}

function toPixelBox(box) {
  return { x: box.x * canvas.width, y: box.y * canvas.height, w: box.w * canvas.width, h: box.h * canvas.height };
}

function clampBox(box) {
  let x = Math.max(0, Math.min(1, Number(box.x)));
  let y = Math.max(0, Math.min(1, Number(box.y)));
  let w = Math.max(0.002, Math.min(1, Number(box.w)));
  let h = Math.max(0.002, Math.min(1, Number(box.h)));
  if (x + w > 1) x = 1 - w;
  if (y + h > 1) y = 1 - h;
  return { ...box, x, y, w, h };
}

function hitTest(point) {
  const handle = 8;
  for (let i = state.boxes.length - 1; i >= 0; i--) {
    const b = toPixelBox(state.boxes[i]);
    const corners = [
      ["nw", b.x, b.y], ["ne", b.x + b.w, b.y], ["sw", b.x, b.y + b.h], ["se", b.x + b.w, b.y + b.h],
    ];
    for (const [name, x, y] of corners) {
      if (Math.abs(point.x - x) <= handle && Math.abs(point.y - y) <= handle) return { index: i, mode: name };
    }
    if (point.x >= b.x && point.x <= b.x + b.w && point.y >= b.y && point.y <= b.y + b.h) return { index: i, mode: "move" };
  }
  return null;
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
    const labelWidth = Math.max(100, Math.min(canvas.width - p.x, ctx.measureText(label).width + 12));
    ctx.fillStyle = color;
    ctx.fillRect(p.x, Math.max(0, p.y - 22), labelWidth, 22);
    ctx.fillStyle = "#fff";
    ctx.fillText(label, p.x + 5, Math.max(14, p.y - 7));
    if (idx === state.selectedIndex) drawHandles(p);
  });
  if (state.drawing) {
    const box = state.drawing;
    ctx.strokeStyle = "#ffffff";
    ctx.setLineDash([6, 4]);
    ctx.strokeRect(Math.min(box.x1, box.x2), Math.min(box.y1, box.y2), Math.abs(box.x2 - box.x1), Math.abs(box.y2 - box.y1));
    ctx.setLineDash([]);
  }
}

function drawHandles(p) {
  ctx.fillStyle = "#fff";
  for (const [x, y] of [[p.x, p.y], [p.x + p.w, p.y], [p.x, p.y + p.h], [p.x + p.w, p.y + p.h]]) {
    ctx.fillRect(x - 4, y - 4, 8, 8);
  }
}

canvas.addEventListener("mousedown", event => {
  const p = canvasPoint(event);
  const hit = hitTest(p);
  if (hit) {
    selectBox(hit.index);
    state.drag = { ...hit, start: p, original: { ...state.boxes[hit.index] } };
    return;
  }
  if (!$("#label-select").value) {
    showToast("请先选择标签", "error");
    return;
  }
  state.selectedIndex = -1;
  state.drawing = { x1: p.x, y1: p.y, x2: p.x, y2: p.y };
});

canvas.addEventListener("mousemove", event => {
  const p = canvasPoint(event);
  if (state.drag) {
    dragSelected(p);
    return;
  }
  if (!state.drawing) return;
  state.drawing.x2 = p.x;
  state.drawing.y2 = p.y;
  draw();
});

canvas.addEventListener("mouseup", () => {
  if (state.drag) {
    state.drag = null;
    scheduleSave();
    return;
  }
  if (!state.drawing) return;
  const box = toNormBox(state.drawing);
  state.drawing = null;
  if (box.w < 0.005 || box.h < 0.005) {
    showToast("框太小，已忽略", "error");
    draw();
    return;
  }
  state.boxes.push({
    label_code: $("#label-select").value,
    track_id: $("#track-id").value || null,
    x: box.x, y: box.y, w: box.w, h: box.h,
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

function scheduleSave() {
  const payload = currentSavePayload();
  if (!payload) return;
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
  const payload = currentSavePayload();
  if (payload) await saveFramePayload(payload);
  await state.saving;
}

async function saveFramePayload(payload) {
  clearTimeout(state.saveTimer);
  state.saveTimer = null;
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
$("#prev-frame").addEventListener("click", () => goFrame(-1));
$("#next-frame").addEventListener("click", () => goFrame(1));
$("#clear-boxes-btn").addEventListener("click", clearCurrentFrameBoxes);

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
      track_id: $("#track-id").value || null,
    });
    $("#track-id").value = track.id;
    if (state.selectedIndex >= 0) {
      state.boxes[state.selectedIndex].track_id = track.id;
      state.boxes[state.selectedIndex].is_keyframe = true;
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
    if (!Number.isFinite(conf) || conf < 0.05 || conf > 0.95) {
      throw new Error("预标注置信度需要在 0.05 到 0.95 之间");
    }
    const startText = new Date().toLocaleTimeString();
    button.disabled = true;
    button.textContent = "预标注运行中...";
    updatePrelabelStatus(`预标注运行中，开始时间 ${startText}`, "running");
    await new Promise(requestAnimationFrame);
    const result = await apiPost("/api/prelabel", { frame_set_id: state.frameSetId, model_path: modelPath, conf });
    updatePrelabelStatus(`整个帧集共生成 ${result.created} 个待确认框；当前画面只显示当前帧的框`, "done");
    showToast(`整个帧集共生成 ${result.created} 个待确认框`);
    await loadBoxes();
    draw();
  } catch (error) {
    updatePrelabelStatus(`预标注失败：${error.message}`, "error");
    showToast(error.message, "error");
  } finally {
    button.disabled = false;
    button.textContent = "运行预标注";
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

function isTypingTarget(target) {
  const tagName = target?.tagName?.toLowerCase();
  return target?.isContentEditable || ["input", "textarea"].includes(tagName);
}

document.addEventListener("keydown", event => {
  if (isTypingTarget(event.target) || event.altKey || event.metaKey) return;
  const key = event.key.toLowerCase();
  if (event.ctrlKey && (event.code === "KeyO" || key === "o")) {
    event.preventDefault();
    clearCurrentFrameBoxes();
    return;
  }
  if (event.ctrlKey) return;
  if (event.code === "KeyA" || key === "a") {
    event.preventDefault();
    goFrame(-1);
  } else if (event.code === "KeyD" || key === "d") {
    event.preventDefault();
    goFrame(1);
  }
}, true);

window.addEventListener("resize", () => {
  if (image.complete && image.style.display !== "none") {
    fitCanvas();
    draw();
  }
});

initAnnotator().catch(error => showToast(error.message, "error"));
