const DETECT_SERIES = [
  { id: "train_loss", label: "训练误差", color: "#2866d6", keys: ["train/box_loss", "box_loss"] },
  { id: "val_loss", label: "验证误差", color: "#e07a2f", keys: ["val/box_loss"] },
  { id: "score", label: "综合评分", color: "#197a4b", keys: ["metrics/mAP50(B)", "metrics/mAP50"] },
];

// 每种任务展示自身的质量指标，不能把检测框mAP标为分割综合评分。
function seriesDefs(task = "detect") {
  if (task === "semantic_segment") return [
    {label:"训练交叉熵",color:"#2866d6",keys:["train/ce_loss"]},
    {label:"验证交叉熵",color:"#e07a2f",keys:["val/ce_loss"]},
    {label:"类别区域 mIoU",color:"#197a4b",keys:["metrics/mIoU"]},
    {label:"像素准确率",color:"#a24aa4",keys:["metrics/pixel_acc"]},
  ];
  if (task === "instance_segment") return [
    {label:"训练mask误差",color:"#2866d6",keys:["train/seg_loss"]},
    {label:"验证mask误差",color:"#e07a2f",keys:["val/seg_loss"]},
    {label:"实例mask mAP50",color:"#197a4b",keys:["metrics/mAP50(M)"]},
    {label:"检测框 mAP50",color:"#a24aa4",keys:["metrics/mAP50(B)"]},
  ];
  return DETECT_SERIES;
}
const TASK_LABELS = {detect:"目标检测",instance_segment:"实例分割",semantic_segment:"语义分割"};

function metricValue(row, candidates) {
  for (const key of candidates) {
    if (row[key] !== undefined && row[key] !== "") return Number(row[key]);
  }
  return null;
}

function drawChart(canvas, rows, task) {
  const ctx = canvas.getContext("2d");
  const width = canvas.width = canvas.clientWidth;
  const height = canvas.height = canvas.clientHeight;
  ctx.clearRect(0, 0, width, height);
  ctx.strokeStyle = "#dfe5ef";
  ctx.lineWidth = 1;
  for (let i = 1; i < 4; i++) {
    const y = (height / 4) * i;
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(width, y);
    ctx.stroke();
  }
  for (const def of seriesDefs(task)) {
    const points = rows.map((row, idx) => ({ idx, value: metricValue(row, def.keys) })).filter(p => Number.isFinite(p.value));
    if (points.length < 2) continue;
    const min = Math.min(...points.map(p => p.value));
    const max = Math.max(...points.map(p => p.value));
    ctx.strokeStyle = def.color;
    ctx.lineWidth = 2;
    ctx.beginPath();
    points.forEach((p, i) => {
      const x = points.length === 1 ? 0 : (p.idx / Math.max(1, rows.length - 1)) * width;
      const y = height - ((p.value - min) / Math.max(0.0001, max - min)) * (height - 16) - 8;
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    });
    ctx.stroke();
  }
}

let trainingBootstrapData = null;
let trainingStatusRefreshInFlight = false;
let modelProfiles = [];

// 型号列表由服务端共同目录提供，页面不自行构造模型文件名。
function renderModelProfiles(task) {
  const form = $("#train-form");
  const old = form.model_profile_id.value;
  const available = modelProfiles.filter(item => item.task_type === task);
  fillSelect(form.model_profile_id, available, item => item.id, item => `${item.label} · ${item.name}`);
  form.model_profile_id.value = available.some(item => item.id === old) ? old : (available.find(item => item.default)?.id || "");
  updateModelStatus();
}

function updateModelStatus() {
  const row = modelProfiles.find(item => item.id === $("#train-form").model_profile_id.value);
  const labels = {not_prepared:"尚未准备，首次训练会下载",cached:"已缓存，使用前校验",ready:"已就绪",preparing:"准备中",failed:"准备失败"};
  $("#model-profile-status").textContent = row ? `${row.name}：${labels[row.status] || row.status}${row.error ? ` · ${row.error}` : ""}` : "请选择可用型号";
}

function fillTrainSelects(data) {
  fillSelect($("#train-form select[name=project_id]"), data.projects, item => item.id, item => item.name, "选择产品");
  fillSelect($("#train-form select[name=dataset_version_id]"), data.datasets, item => item.id, item => `${item.name} · ${TASK_LABELS[item.metadata?.task_type || "detect"]} (${item.status})`, "选择训练数据集");
  updateImgSizeRecommendation(data.datasets);
}

function datasetRecommendedImgsz(dataset) {
  const metadata = dataset?.metadata || {};
  const summary = dataset?.summary || {};
  return Number(
    metadata.recommended_imgsz
      || summary.recommended_imgsz
      || metadata.image_size_stats?.recommended_imgsz
      || summary.image_size_stats?.recommended_imgsz
      || 0
  );
}

function updateImgSizeRecommendation(datasets) {
  const form = $("#train-form");
  const hint = $("#imgsz-recommendation");
  if (!form || !hint) return;
  const dataset = (datasets || []).find(item => item.id === form.dataset_version_id.value);
  if (dataset) form.project_id.value = dataset.project_id;
  const task = dataset?.metadata?.task_type || "detect";
  $("#train-task-hint").textContent = dataset ? `任务固定为${TASK_LABELS[task]}；默认小模型，不同任务不能混用。` : "请选择数据集，任务类型由数据集决定。";
  renderModelProfiles(task);
  const recommended = datasetRecommendedImgsz(dataset);
  const stats = dataset?.metadata?.image_size_stats || dataset?.summary?.image_size_stats || {};
  if (recommended) {
    const longEdge = stats.long_edge_avg ? `，平均长边 ${stats.long_edge_avg}` : "";
    hint.textContent = `推荐输入尺寸：${recommended}${longEdge}。留空会自动使用推荐值；手动填写则覆盖。`;
  } else {
    hint.textContent = "输入尺寸默认按训练数据集图片尺寸自动推荐；需要时可手动填写覆盖。";
  }
}

function statusText(status) {
  const map = {
    queued: "排队中",
    running: "训练中",
    stopped: "已停止",
    finished: "已完成",
    failed: "失败",
  };
  return map[status] || status || "-";
}

function phaseText(job) {
  return job.progress?.phase_text || statusText(job.status);
}

function supportText(job) {
  if (job.status === "running" && Number(job.progress?.current_epoch || 0) === 0) {
    return "训练初始化阶段可能需要加载模型、检查数据集和初始化显卡，请稍候。";
  }
  return "";
}

function renderTrainJobs(trainJobs) {
  $("#train-list").innerHTML = trainJobs.map(job => {
    const p = job.progress || {};
    const canStop = job.status === "running" || job.status === "queued";
    const modelPackage = job.model_package;
    const hasModel = modelPackage || (p.model_files && Object.keys(p.model_files).length > 0);
    const packageText = modelPackage
      ? `模型目录已生成：${esc(modelPackage.package_dir)}`
      : hasModel
        ? "检测到模型文件，正在整理到模型仓库"
        : "尚未产生可用模型";
    const hint = supportText(job);
    return rowHtml(
      esc(job.name),
      `
        状态: ${esc(statusText(job.status))} | 阶段: ${esc(phaseText(job))} | 进度: ${p.current_epoch || 0}/${p.total_epochs || "-"} | 预计剩余: ${secondsText(p.eta_seconds)}
        <div class="progress-shell"><div class="progress-fill" style="width:${Number(p.percent || 0)}%"></div></div>
        <div class="row-meta">${packageText}</div>
        ${hint ? `<div class="row-meta">${esc(hint)}</div>` : ""}
        <div class="row-meta">任务：${esc(TASK_LABELS[job.params?.task_type || "detect"])}</div>
        <div class="row-meta">型号：${esc(job.params?.model_name || "历史自定义模型")}</div>
        ${job.status === "failed" ? `<div class="row-meta">${esc(job.log_text || "训练失败，请检查日志")}</div>` : ""}
        ${job.model_package_error ? `<div class="row-meta">模型整理失败：${esc(job.model_package_error)}</div>` : ""}
        <div class="chart-legend">${seriesDefs(job.params?.task_type).map(def => `<span><i style="background:${def.color}"></i>${def.label}</span>`).join("")}</div>
        <div class="row-meta">${seriesDefs(job.params?.task_type).map(def => `${def.label}: ${metricValue(p.last_metrics || {}, def.keys) ?? "待训练"}`).join(" · ")}</div>
        <canvas class="chart" data-job="${esc(job.id)}"></canvas>
      `,
      `
        ${canStop ? `<button data-stop="${esc(job.id)}">停止</button>` : ""}
        ${hasModel ? `<a class="button-link" href="/packages?train_job_id=${esc(job.id)}">查看模型</a>` : ""}
      `
    );
  }).join("");
  for (const job of trainJobs) {
    const canvas = document.querySelector(`canvas[data-job="${job.id}"]`);
    if (canvas) drawChart(canvas, job.progress?.series || [], job.params?.task_type);
  }
  $$("[data-stop]").forEach(btn => {
    btn.onclick = async () => {
      try {
        await apiPost(`/api/train-jobs/${btn.dataset.stop}/stop`, {});
        showToast("训练停止命令已发送，若已有模型文件会自动整理到模型仓库。");
        await refreshTrainingStatus();
      } catch (error) {
        showToast(error.message, "error");
      }
    };
  });
}

async function refreshTrainingStatus() {
  if (trainingStatusRefreshInFlight) return;
  trainingStatusRefreshInFlight = true;
  try {
    const data = await loadBootstrap();
    renderTrainJobs(data.train_jobs || []);
    await renderGpuStatus();
  } finally {
    trainingStatusRefreshInFlight = false;
  }
}

async function initializeTrainingPage() {
  modelProfiles = (await apiGet("/api/model-profiles")).profiles;
  trainingBootstrapData = await loadBootstrap();
  fillTrainSelects(trainingBootstrapData);
  renderTrainJobs(trainingBootstrapData.train_jobs || []);
  await renderGpuStatus();
}

async function renderGpuStatus() {
  const gpu = await apiGet("/api/gpu-status");
  $("#gpu-status").innerHTML = gpu.ok
    ? gpu.gpus.map(item => `显卡: ${esc(item.name)} | 显存 ${item.memory_used_mb}/${item.memory_total_mb} MB | 利用率 ${item.utilization_gpu}%`).join("<br>")
    : `显卡状态不可用: ${esc(gpu.error || "")}`;
}

$("#train-form").addEventListener("submit", async event => {
  event.preventDefault();
  const form = event.currentTarget;
  const submit = form.querySelector("button[type=submit]");
  submit.disabled = true;
  try {
    $("#model-profile-status").textContent = "正在校验或准备模型；不会自动更换所选型号。";
    await apiPost("/api/train-jobs", {
      project_id: form.project_id.value,
      dataset_version_id: form.dataset_version_id.value,
      name: form.name.value,
      base_model_path: form.base_model_path.value.trim(),
      model_profile_id: form.base_model_path.value.trim() ? null : form.model_profile_id.value,
      params: {
        epochs: Number(form.epochs.value),
        patience: Number(form.patience.value),
        imgsz: form.imgsz.value ? Number(form.imgsz.value) : null,
        batch: Number(form.batch.value),
        device: form.device.value,
      },
    });
    form.base_model_path.value = "";
    showToast("模型训练任务已创建，后台开始运行。");
    await refreshTrainingStatus();
  } catch (error) {
    $("#model-profile-status").textContent = error.message;
    showToast(error.message, "error");
  } finally {
    submit.disabled = false;
  }
});

$("#train-form select[name=model_profile_id]").addEventListener("change", updateModelStatus);
$("#prepare-model").addEventListener("click", async event => {
  const row = modelProfiles.find(item => item.id === $("#train-form").model_profile_id.value);
  if (!row) return;
  event.currentTarget.disabled = true;
  $("#model-profile-status").textContent = `${row.name}：准备中，请稍候`;
  try {
    await apiPost(`/api/model-profiles/${encodeURIComponent(row.id)}/prepare?task=${encodeURIComponent(row.task_type)}`, {});
    modelProfiles = (await apiGet("/api/model-profiles")).profiles;
    updateModelStatus();
  } catch (error) {
    $("#model-profile-status").textContent = error.message;
    showToast(error.message, "error");
  } finally {
    $("#prepare-model").disabled = false;
  }
});

$("#train-form select[name=dataset_version_id]").addEventListener("change", () => {
  updateImgSizeRecommendation(trainingBootstrapData?.datasets || []);
});

initializeTrainingPage().finally(() => setInterval(refreshTrainingStatus, 6000));
