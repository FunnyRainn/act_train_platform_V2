async function refreshPackages() {
  const data = await loadBootstrap();
  const params = new URLSearchParams(location.search);
  const focusJob = params.get("train_job_id");
  fillSelect(
    $("#package-form select[name=train_job_id]"),
    data.train_jobs,
    item => item.id,
    item => `${item.name} (${item.status})`,
    "选择已产生模型文件的训练任务"
  );
  if (focusJob) $("#package-form select[name=train_job_id]").value = focusJob;
  $("#package-list").innerHTML = data.packages.map(pkg => {
    const focus = pkg.train_job_id === focusJob ? " selected" : "";
    return `<div class="row${focus}">
      <div>
        <div class="row-title">${esc(pkg.name)}</div>
        <div class="row-meta">状态: ${esc(pkg.status)} | 训练任务: ${esc(pkg.train_job_id)} | 目录: ${esc(pkg.package_dir)}</div>
      </div>
      <div></div>
    </div>`;
  }).join("");
}

$("#package-form").addEventListener("submit", async event => {
  event.preventDefault();
  try {
    await apiPost("/api/model-packages", formToObject(event.currentTarget));
    showToast("模型目录已生成");
    await refreshPackages();
  } catch (error) {
    showToast(error.message, "error");
  }
});

refreshPackages();
