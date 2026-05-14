async function refreshDatasets() {
  const data = await loadBootstrap();
  fillSelect($("#dataset-form select[name=project_id]"), data.projects, item => item.id, item => item.name, "选择项目");
  fillMultiSelect($("#dataset-form select[name=frame_set_ids]"), data.frame_sets, item => item.id, item => `${item.name} (${item.frame_count}帧)`);
  fillMultiSelect($("#dataset-form select[name=history_dataset_ids]"), data.datasets, item => item.id, item => `${item.name} (${item.status})`);
  $("#dataset-list").innerHTML = data.datasets.map(ds => rowHtml(
    esc(ds.name),
    `状态: ${esc(ds.status)} | 标签: ${esc(ds.label_codes.join(", "))} | 样本: ${esc(JSON.stringify(ds.summary))} | ${esc(ds.output_dir)}`
  )).join("");
}

$("#dataset-form").addEventListener("submit", async event => {
  event.preventDefault();
  try {
    const payload = formToObject(event.currentTarget);
    if (!payload.history_dataset_ids?.length) {
      showToast("提示：本次未混入历史数据集，请确认不会影响旧标签能力", "warn");
    }
    await apiPost("/api/datasets/export", payload);
    showToast("数据集版本已导出");
    await refreshDatasets();
  } catch (error) {
    showToast(error.message, "error");
  }
});

refreshDatasets();
