async function refreshDatasets() {
  const data = await loadBootstrap();
  fillSelect($("#dataset-form select[name=project_id]"), data.projects, item => item.id, item => item.name, "选择产品");
  fillMultiSelect($("#dataset-form select[name=frame_set_ids]"), data.frame_sets, item => item.id, item => `${item.name} (${item.frame_count}帧)`);
  fillMultiSelect($("#dataset-form select[name=history_dataset_ids]"), data.datasets, item => item.id, item => `${item.name} (${item.status})`);
  $("#dataset-list").innerHTML = data.datasets.map(ds => {
    const summary = ds.summary || {};
    const modeText = summary.export_mode === "annotated_only" ? "只导出已标注帧" : "已确认标注";
    return rowHtml(
      esc(ds.name),
      `状态: ${esc(ds.status)} | 模式: ${modeText} | 标签: ${esc(ds.label_codes.join(", "))} | 样本: ${esc(JSON.stringify(summary))} | ${esc(ds.output_dir)}`
    );
  }).join("");
}

async function exportDataset(annotatedOnly = false) {
  const form = $("#dataset-form");
  const payload = formToObject(form);
  payload.annotated_only = annotatedOnly;
  if (annotatedOnly && !payload.name.includes("已标注帧")) {
    payload.name = `${payload.name} - 已标注帧`;
  }
  if (!payload.history_dataset_ids?.length) {
    showToast("提示：本次未混入历史数据集，请确认不会影响旧标签能力", "warn");
  }
  await apiPost("/api/datasets/export", payload);
  showToast(annotatedOnly ? "已标注帧训练数据集已导出" : "训练数据集已导出");
  await refreshDatasets();
}

$("#dataset-form").addEventListener("submit", async event => {
  event.preventDefault();
  try {
    await exportDataset(false);
  } catch (error) {
    showToast(error.message, "error");
  }
});

$("#export-annotated-only").addEventListener("click", async () => {
  try {
    await exportDataset(true);
  } catch (error) {
    showToast(error.message, "error");
  }
});

refreshDatasets();
