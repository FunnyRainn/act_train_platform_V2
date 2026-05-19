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
};

const canvas = $("#bbox-canvas");
const ctx = canvas.getContext("2d");
const image = $("#frame-image");

async function initAnnotator() {
  state.bootstrap = await loadBootstrap();
  fillSelect($("#frame-set-select"), state.bootstrap.frame_sets, item => item.id, item => `${item.name} (${item.frame_count}帧)`, "选择帧集");
  fillSelect($("#label-select"), state.bootstrap.labels.filter(x => x.enabled), item => item.code, item => `${item.code} ${item.name}`, "选择标签");
}

async function loadFrameSet(frameSetId) {
  if (!frameSetId) return;
  state.frameSetId = frameSetId;
  state.frames = await apiGet(`/api/frame-sets/${frameSetId}/frames`);
  state.frameIndex = 0;
  await showFrame();
}

function currentFrame() {
  return state.frames[state.frameIndex];
}

async function showFrame() {
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
  $("#frame-info").textContent = `${state.frameIndex + 1}/${state.frames.length} | 原始帧号 ${frame.frame_index}`;
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
  const frame = currentFrame();
  state.boxes = await apiGet(`/api/frame-sets/${state.frameSetId}/annotations?frame_id=${frame.id}`);
  state.selectedIndex = -1;
  renderBoxList();
}

function renderBoxList() {
  $("#box-list").innerHTML = state.boxes.map((box, idx) => `
    <div class="box-item ${idx === state.selectedIndex ? "selected" : ""}">
      <strong>${esc(box.label_code)}</strong>
      ${box.track_id ? `<span>跟踪对象 ${esc(box.track_id.slice(-6))}</span>` : ""}
      <div>来源: ${sourceText(box.source)} | ${box.is_keyframe ? "关键帧" : "普通帧"} | ${box.confirmed ? "已确认" : "待确认"}</div>
      <button data-select="${idx}">选中</button>
      ${box.source === "prelabel" && !box.confirmed ? `<button data-confirm="${idx}">确认</button>` : ""}
      <button data-delete="${idx}">删除</button>
    </div>
  `).join("");
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
    ctx.strokeStyle = idx === state.selectedIndex ? "#ffffff" : color;
    ctx.lineWidth = idx === state.selectedIndex ? 3 : 2;
    ctx.strokeRect(p.x, p.y, p.w, p.h);
    ctx.fillStyle = color;
    ctx.fillRect(p.x, Math.max(0, p.y - 22), 142, 22);
    ctx.fillStyle = "#fff";
    ctx.font = "13px Microsoft YaHei";
    ctx.fillText(`${box.label_code} ${sourceText(box.source)}`, p.x + 5, Math.max(14, p.y - 7));
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
  $("#save-status").textContent = "保存中...";
  clearTimeout(state.saveTimer);
  state.saveTimer = setTimeout(() => saveCurrentFrame(), 450);
}

async function saveCurrentFrame() {
  if (!state.frameSetId || !currentFrame()) return;
  try {
    const frameSet = state.bootstrap.frame_sets.find(item => item.id === state.frameSetId);
    await apiPost("/api/annotations/frame", {
      project_id: frameSet.project_id,
      frame_set_id: state.frameSetId,
      frame_id: currentFrame().id,
      annotations: state.boxes,
    });
    $("#save-status").textContent = "已保存";
  } catch (error) {
    $("#save-status").textContent = "保存失败";
    showToast(error.message, "error");
  }
}

$("#frame-set-select").addEventListener("change", event => loadFrameSet(event.target.value));
$("#prev-frame").addEventListener("click", async () => { if (state.frameIndex > 0) { await saveCurrentFrame(); state.frameIndex--; await showFrame(); } });
$("#next-frame").addEventListener("click", async () => { if (state.frameIndex < state.frames.length - 1) { await saveCurrentFrame(); state.frameIndex++; await showFrame(); } });
$("#clear-boxes-btn").addEventListener("click", () => { state.boxes = []; state.selectedIndex = -1; scheduleSave(); renderBoxList(); draw(); });

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
    const frameSet = state.bootstrap.frame_sets.find(item => item.id === state.frameSetId);
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
    await saveCurrentFrame();
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
  try {
    const modelPath = $("#prelabel-model").value.trim();
    if (!modelPath) throw new Error("请填写旧模型路径");
    const conf = Number($("#prelabel-conf").value || 0.25);
    if (!Number.isFinite(conf) || conf < 0.05 || conf > 0.95) {
      throw new Error("预标注置信度需要在 0.05 到 0.95 之间");
    }
    const result = await apiPost("/api/prelabel", { frame_set_id: state.frameSetId, model_path: modelPath, conf });
    showToast(`预标注完成，生成 ${result.created} 个待确认框`);
    await loadBoxes();
    draw();
  } catch (error) {
    showToast(error.message, "error");
  }
});

window.addEventListener("resize", () => {
  if (image.complete && image.style.display !== "none") {
    fitCanvas();
    draw();
  }
});

initAnnotator().catch(error => showToast(error.message, "error"));
