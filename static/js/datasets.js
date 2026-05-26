let datasetData = null;

function datasetSummaryText(summary) {
  const modeText = summary.export_mode === "annotated_only" ? "只导出已标注帧" : "已确认标注";
  const historyText = Number(summary.history_images || 0) > 0
    ? `历史混入: ${summary.history_images}张/${summary.history_boxes || 0}框`
    : "历史混入: 无";
  return [
    `模式: ${modeText}`,
    `当前帧: ${summary.current_frames || 0}张/${summary.current_boxes || 0}框`,
    historyText,
    `已确认预标注: ${summary.confirmed_prelabel_boxes || 0}框`,
    `跳过未确认预标注: ${summary.skipped_unconfirmed_prelabel_boxes || 0}框`,
    `跳过区域外框: ${summary.skipped_outside_focus_region || 0}框`,
    `跳过未标注帧: ${summary.skipped_unannotated || 0}`,
    `总计: train ${summary.train || 0} / val ${summary.val || 0} / test ${summary.test || 0}`,
  ].join(" | ");
}

function datasetScopeText(ds) {
  const meta = ds.metadata || {};
  if (meta.image_scope === "focus_region_crop") {
    return `关注区域: ${meta.focus_region_name || meta.focus_region_id || "-"}`;
  }
  return "整图";
}

function renderFocusExportPanel() {
  const panel = $("#focus-export-panel");
  const list = $("#focus-export-list");
  const projectId = $("#dataset-form select[name=project_id]").value;
  const scope = $("#dataset-image-scope").value;
  if (!panel || !list) return;
  panel.classList.toggle("hidden", scope !== "focus_region_crop");
  if (scope !== "focus_region_crop") return;
  const regions = (datasetData?.focus_regions || []).filter(item => item.project_id === projectId && Number(item.enabled) !== 0);
  const histories = (datasetData?.datasets || []).filter(item => item.project_id === projectId);
  list.innerHTML = regions.length ? regions.map(region => `
    <div class="focus-export-item">
      <label class="inline"><input type="checkbox" data-focus-region="${esc(region.id)}"> ${esc(region.name)}</label>
      <select multiple size="4" data-focus-history="${esc(region.id)}">
        ${histories.map(ds => `<option value="${esc(ds.id)}">${esc(ds.name)} | ${esc(datasetScopeText(ds))}</option>`).join("")}
      </select>
    </div>
  `).join("") : `<div class="notice">当前产品还没有关注区域，请先到标注工作台创建并锁定关注区域。</div>`;
}

async function refreshDatasets() {
  const data = await loadBootstrap();
  datasetData = data;
  fillSelect($("#dataset-form select[name=project_id]"), data.projects, item => item.id, item => item.name, "选择产品");
  fillMultiSelect($("#dataset-form select[name=frame_set_ids]"), data.frame_sets, item => item.id, item => `${item.name} (${item.frame_count}帧)`);
  fillMultiSelect($("#dataset-form select[name=history_dataset_ids]"), data.datasets, item => item.id, item => `${item.name} (${item.status}) | ${datasetScopeText(item)}`);
  $("#dataset-list").innerHTML = data.datasets.map(ds => {
    const summary = ds.summary || {};
    return rowHtml(
      esc(ds.name),
      `状态: ${esc(ds.status)} | 视野: ${esc(datasetScopeText(ds))} | ${esc(datasetSummaryText(summary))} | 标签: ${esc(ds.label_codes.join(", "))} | ${esc(ds.output_dir)}`
    );
  }).join("");
  renderFocusExportPanel();
}

function collectFocusExportConfig(payload) {
  payload.focus_region_ids = [];
  payload.history_by_focus_region = {};
  if (payload.image_scope !== "focus_region_crop") return;
  $$("[data-focus-region]").forEach(input => {
    if (!input.checked) return;
    const regionId = input.dataset.focusRegion;
    payload.focus_region_ids.push(regionId);
    const select = document.querySelector(`[data-focus-history="${CSS.escape(regionId)}"]`);
    payload.history_by_focus_region[regionId] = Array.from(select?.selectedOptions || []).map(option => option.value);
  });
}

async function exportDataset(annotatedOnly = false) {
  const form = $("#dataset-form");
  const payload = formToObject(form);
  payload.frame_set_ids = payload.frame_set_ids || [];
  payload.history_dataset_ids = payload.history_dataset_ids || [];
  payload.annotated_only = annotatedOnly;
  collectFocusExportConfig(payload);
  if (payload.image_scope === "focus_region_crop" && !payload.focus_region_ids.length) {
    throw new Error("请选择至少一个关注区域");
  }
  const hasFocusHistory = Object.values(payload.history_by_focus_region || {}).some(list => Array.isArray(list) && list.length);
  if (!payload.frame_set_ids.length && !payload.history_dataset_ids.length && !hasFocusHistory) {
    throw new Error("请至少选择一个帧集或一个历史训练数据集");
  }
  if (annotatedOnly && !payload.name.includes("已标注帧")) {
    payload.name = `${payload.name} - 已标注帧`;
  }
  if (!payload.history_dataset_ids.length && !hasFocusHistory) {
    showToast("提示：本次未混入历史数据集，请确认不会影响旧标签能力", "warn");
  }
  const result = await apiPost("/api/datasets/export", payload);
  const created = result.created ? `，共生成 ${result.created} 个版本` : "";
  showToast((annotatedOnly ? "已标注帧训练数据集已导出" : "训练数据集已导出") + created);
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

$("#dataset-form select[name=project_id]").addEventListener("change", renderFocusExportPanel);
$("#dataset-image-scope").addEventListener("change", renderFocusExportPanel);

refreshDatasets();
