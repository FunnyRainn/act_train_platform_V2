async function refreshTraining() {
  const data = await loadBootstrap();
  fillSelect($("#train-form select[name=project_id]"), data.projects, item => item.id, item => item.name, "选择项目");
  fillSelect($("#train-form select[name=dataset_version_id]"), data.datasets, item => item.id, item => `${item.name} (${item.status})`, "选择数据集");
  $("#train-list").innerHTML = data.train_jobs.map(job => rowHtml(
    esc(job.name),
    `状态: ${esc(job.status)} | 数据集: ${esc(job.dataset_version_id)} | 输出: ${esc(job.output_dir)}<br>${esc(job.log_text || "")}`
  )).join("");
}

$("#train-form").addEventListener("submit", async event => {
  event.preventDefault();
  try {
    const form = event.currentTarget;
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
    showToast("训练任务已创建，后台开始运行");
    await refreshTraining();
  } catch (error) {
    showToast(error.message, "error");
  }
});

refreshTraining();
setInterval(refreshTraining, 8000);
