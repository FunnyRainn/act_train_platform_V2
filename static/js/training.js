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
  const seriesDefs = [
    { color: "#2866d6", keys: ["train/box_loss", "box_loss"] },
    { color: "#e07a2f", keys: ["val/box_loss"] },
    { color: "#197a4b", keys: ["metrics/mAP50(B)", "metrics/mAP50"] },
  ];
  for (const def of seriesDefs) {
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

async function refreshTraining() {
  const data = await loadBootstrap();
  fillSelect($("#train-form select[name=project_id]"), data.projects, item => item.id, item => item.name, "选择产品");
  fillSelect($("#train-form select[name=dataset_version_id]"), data.datasets, item => item.id, item => `${item.name} (${item.status})`, "选择训练数据集");
  await renderGpuStatus();
  $("#train-list").innerHTML = data.train_jobs.map(job => {
    const p = job.progress || {};
    const canStop = job.status === "running" || job.status === "queued";
    const hasModel = p.model_files && Object.keys(p.model_files).length > 0;
    return rowHtml(
      esc(job.name),
      `
        状态: ${esc(job.status)} | 进度: ${p.current_epoch || 0}/${p.total_epochs || "-"} | 预计剩余: ${secondsText(p.eta_seconds)}
        <div class="progress-shell"><div class="progress-fill" style="width:${Number(p.percent || 0)}%"></div></div>
        输出: ${esc(job.output_dir)}<br>${esc(job.log_text || "")}
        <canvas class="chart" data-job="${esc(job.id)}"></canvas>
      `,
      `
        ${canStop ? `<button data-stop="${esc(job.id)}">停止</button>` : ""}
        ${hasModel ? `<a class="button-link" href="/packages?train_job_id=${esc(job.id)}">查看模型</a>` : ""}
      `
    );
  }).join("");
  for (const job of data.train_jobs) {
    const canvas = document.querySelector(`canvas[data-job="${job.id}"]`);
    if (canvas) drawChart(canvas, job.progress?.series || []);
  }
  $$("[data-stop]").forEach(btn => {
    btn.onclick = async () => {
      try {
        await apiPost(`/api/train-jobs/${btn.dataset.stop}/stop`, {});
        showToast("训练停止命令已发送");
        await refreshTraining();
      } catch (error) {
        showToast(error.message, "error");
      }
    };
  });
}

async function renderGpuStatus() {
  const gpu = await apiGet("/api/gpu-status");
  $("#gpu-status").innerHTML = gpu.ok
    ? gpu.gpus.map(item => `显卡: ${esc(item.name)} | 显存 ${item.memory_used_mb}/${item.memory_total_mb} MB | 利用率 ${item.utilization_gpu}%`).join("<br>")
    : `显卡状态不可用：${esc(gpu.error || "")}`;
}

$("#train-form").addEventListener("submit", async event => {
  event.preventDefault();
  const form = event.currentTarget;
  try {
    await apiPost("/api/train-jobs", {
      project_id: form.project_id.value,
      dataset_version_id: form.dataset_version_id.value,
      name: form.name.value,
      base_model_path: form.base_model_path.value,
      params: {
        epochs: Number(form.epochs.value),
        imgsz: Number(form.imgsz.value),
        batch: Number(form.batch.value),
        device: form.device.value,
      },
    });
    showToast("模型训练任务已创建，后台开始运行");
    await refreshTraining();
  } catch (error) {
    showToast(error.message, "error");
  }
});

refreshTraining();
setInterval(refreshTraining, 6000);
