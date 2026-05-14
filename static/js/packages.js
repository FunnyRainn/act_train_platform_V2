async function refreshPackages() {
  const data = await loadBootstrap();
  fillSelect($("#package-form select[name=train_job_id]"), data.train_jobs, item => item.id, item => `${item.name} (${item.status})`, "选择已完成训练任务");
  $("#package-list").innerHTML = data.packages.map(pkg => rowHtml(
    esc(pkg.name),
    `状态: ${esc(pkg.status)} | 目录: ${esc(pkg.package_dir)}`
  )).join("");
}

$("#package-form").addEventListener("submit", async event => {
  event.preventDefault();
  try {
    await apiPost("/api/model-packages", formToObject(event.currentTarget));
    showToast("模型包已导出");
    await refreshPackages();
  } catch (error) {
    showToast(error.message, "error");
  }
});

refreshPackages();
