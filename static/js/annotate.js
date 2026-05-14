let state = {
  bootstrap: null,
  frameSetId: "",
  frames: [],
  frameIndex: 0,
  boxes: [],
  drawing: null,
  trackId: "",
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

function currentFrame() {
  return state.frames[state.frameIndex];
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
  renderBoxList();
}

function renderBoxList() {
  $("#box-list").innerHTML = state.boxes.map((box, idx) => `
    <div class="box-item">
      <strong>${esc(box.label_code)}</strong>
      ${box.track_id ? `<span>轨迹 ${esc(box.track_id)}</span>` : ""}
      <div>来源: ${esc(box.source)} | ${box.is_keyframe ? "关键帧" : "普通帧"} | ${box.confirmed ? "已确认" : "待确认"}</div>
      <button data-idx="${idx}">删除</button>
    </div>
  `).join("");
  $$("#box-list button").forEach(btn => {
    btn.onclick = () => {
      state.boxes.splice(Number(btn.dataset.idx), 1);
      renderBoxList();
      draw();
    };
  });
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
  return { x, y, w, h };
}

function toPixelBox(box) {
  return {
    x: box.x * canvas.width,
    y: box.y * canvas.height,
    w: box.w * canvas.width,
    h: box.h * canvas.height,
  };
}

function draw() {
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  for (const box of state.boxes) {
    const p = toPixelBox(box);
    const color = box.source === "prelabel" && !box.confirmed ? "#f5a623" : box.is_keyframe ? "#1fbf75" : "#2f76ff";
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.strokeRect(p.x, p.y, p.w, p.h);
    ctx.fillStyle = color;
    ctx.fillRect(p.x, Math.max(0, p.y - 22), 120, 22);
    ctx.fillStyle = "#fff";
    ctx.font = "13px Microsoft YaHei";
    ctx.fillText(`${box.label_code} ${box.source}`, p.x + 5, Math.max(14, p.y - 7));
  }
  if (state.drawing) {
    const box = state.drawing;
    ctx.strokeStyle = "#ffffff";
    ctx.setLineDash([6, 4]);
    ctx.strokeRect(Math.min(box.x1, box.x2), Math.min(box.y1, box.y2), Math.abs(box.x2 - box.x1), Math.abs(box.y2 - box.y1));
    ctx.setLineDash([]);
  }
}

canvas.addEventListener("mousedown", event => {
  if (!$("#label-select").value) {
    showToast("请先选择标签", "error");
    return;
  }
  const p = canvasPoint(event);
  state.drawing = { x1: p.x, y1: p.y, x2: p.x, y2: p.y };
});

canvas.addEventListener("mousemove", event => {
  if (!state.drawing) return;
  const p = canvasPoint(event);
  state.drawing.x2 = p.x;
  state.drawing.y2 = p.y;
  draw();
});

canvas.addEventListener("mouseup", () => {
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
    x: box.x,
    y: box.y,
    w: box.w,
    h: box.h,
    source: "manual",
    is_keyframe: $("#is-keyframe").checked,
    confirmed: true,
  });
  renderBoxList();
  draw();
});

$("#frame-set-select").addEventListener("change", event => loadFrameSet(event.target.value));

$("#prev-frame").addEventListener("click", async () => {
  if (state.frameIndex > 0) {
    state.frameIndex -= 1;
    await showFrame();
  }
});

$("#next-frame").addEventListener("click", async () => {
  if (state.frameIndex < state.frames.length - 1) {
    state.frameIndex += 1;
    await showFrame();
  }
});

$("#clear-boxes-btn").addEventListener("click", () => {
  state.boxes = [];
  renderBoxList();
  draw();
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
    showToast("轨迹已准备");
  } catch (error) {
    showToast(error.message, "error");
  }
});

$("#save-frame-btn").addEventListener("click", async () => {
  try {
    const frameSet = state.bootstrap.frame_sets.find(item => item.id === state.frameSetId);
    await apiPost("/api/annotations/frame", {
      project_id: frameSet.project_id,
      frame_set_id: state.frameSetId,
      frame_id: currentFrame().id,
      annotations: state.boxes,
    });
    showToast("当前帧已保存");
    await loadBoxes();
  } catch (error) {
    showToast(error.message, "error");
  }
});

$("#interpolate-btn").addEventListener("click", async () => {
  try {
    const trackId = $("#track-id").value;
    if (!trackId) throw new Error("请先填写轨迹 ID");
    const result = await apiPost(`/api/tracks/${trackId}/interpolate`, { frame_set_id: state.frameSetId });
    showToast(`插值完成，生成 ${result.generated} 个框`);
    await loadBoxes();
  } catch (error) {
    showToast(error.message, "error");
  }
});

$("#prelabel-btn").addEventListener("click", async () => {
  try {
    const modelPath = $("#prelabel-model").value.trim();
    if (!modelPath) throw new Error("请填写旧模型路径");
    const result = await apiPost("/api/prelabel", { frame_set_id: state.frameSetId, model_path: modelPath, conf: 0.25 });
    showToast(`预标注完成，生成 ${result.created} 个待确认框`);
    await loadBoxes();
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
