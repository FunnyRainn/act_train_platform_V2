const SERIES_DEFS = [
  { id: "train_loss", label: "训练误差", color: "#2866d6", keys: ["train/box_loss", "box_loss"] },
  { id: "val_loss", label: "验证误差", color: "#e07a2f", keys: ["val/box_loss"] },
  { id: "score", label: "综合评分", color: "#197a4b", keys: ["metrics/mAP50(B)", "metrics/mAP50"] },
];

function metricValue(row, candidates) {
  for (const key of candidates) {
    if (row[key] !== undefined && row[key] !== "") return Number(row[key]);
  }
  return null;
}

function drawChart(canvas, rows) {
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
  for (const def of SERIES_DEFS) {
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

function fillTrainSelects(data) {
  fillSelect($("#train-form select[name=project_id]"), data.projects, item => item.id, item => item.name, "选择产品");
  fillSelect($("#train-form select[name=dataset_version_id]"), data.datasets, item => item.id, item => `${item.name} (${item.status})`, "选择训练数据集");
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
        <div class="chart-legend">${SERIES_DEFS.map(def => `<span><i style="background:${def.color}"></i>${def.label}</span>`).join("")}</div>
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
    if (canvas) drawChart(canvas, job.progress?.series || []);
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
  try {
    await apiPost("/api/train-jobs", {
      project_id: form.project_id.value,
      dataset_version_id: form.dataset_version_id.value,
      name: form.name.value,
      base_model_path: form.base_model_path.value.trim(),
      params: {
        epochs: Number(form.epochs.value),
        imgsz: form.imgsz.value ? Number(form.imgsz.value) : null,
        batch: Number(form.batch.value),
        device: form.device.value,
      },
    });
    form.base_model_path.value = "";
    showToast("模型训练任务已创建，后台开始运行。");
    await refreshTrainingStatus();
  } catch (error) {
    showToast(error.message, "error");
  }
});

$("#train-form select[name=dataset_version_id]").addEventListener("change", () => {
  updateImgSizeRecommendation(trainingBootstrapData?.datasets || []);
});

initializeTrainingPage().finally(() => setInterval(refreshTrainingStatus, 6000));
