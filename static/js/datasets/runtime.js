let datasetData = null;
let yoloInspectResult = null;

function datasetSummaryText(summary) {
  const modeText = summary.export_mode === "annotated_only"
    ? "只导出已标注帧"
    : summary.export_mode === "external_yolo_import"
      ? "外部 YOLO 导入"
      : "已确认标注";
  const historyText = Number(summary.history_images || 0) > 0
    ? `历史混入: ${summary.history_images}张/${summary.history_boxes || 0}框`
    : "历史混入: 无";
  const negativeText = summary.export_mode === "external_yolo_import"
    ? `负样本/空标签: ${(summary.empty_label_images || 0) + (summary.missing_label_images || 0)}张 | 跳过未映射框: ${summary.skipped_unmapped_boxes || 0}`
    : `已确认预标注: ${summary.confirmed_prelabel_boxes || 0}框 | 跳过未确认预标注: ${summary.skipped_unconfirmed_prelabel_boxes || 0}框`;
  return [
    `模式: ${modeText}`,
    `当前帧/图片: ${summary.current_frames || summary.source_images || 0}张/${summary.current_boxes || summary.source_boxes || 0}框`,
    historyText,
    negativeText,
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

function projectFrameSets(projectId) {
  return (datasetData?.frame_sets || []).filter(item => item.project_id === projectId);
}

function projectDatasets(projectId) {
  return (datasetData?.datasets || []).filter(item => item.project_id === projectId);
}

function projectLabels(projectId) {
  const project = (datasetData?.projects || []).find(item => item.id === projectId);
  const codes = new Set(project?.label_codes || []);
  return (datasetData?.labels || []).filter(label => codes.has(label.code));
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
  const histories = projectDatasets(projectId);
  list.innerHTML = regions.length ? regions.map(region => `
    <div class="focus-export-item">
      <label class="inline"><input type="checkbox" data-focus-region="${esc(region.id)}"> ${esc(region.name)}</label>
      <select multiple size="4" data-focus-history="${esc(region.id)}">
        ${histories.map(ds => `<option value="${esc(ds.id)}">${esc(ds.name)} | ${esc(datasetScopeText(ds))}</option>`).join("")}
      </select>
    </div>
  `).join("") : `<div class="notice">当前产品还没有关注区域，请先到标注工作台创建并锁定关注区域。</div>`;
}

function renderYoloImportOptions() {
  const form = $("#yolo-import-form");
  if (!form || !datasetData) return;
  const projectId = form.project_id.value;
  const scope = form.image_scope.value;
  const focusWrap = $("#yolo-import-focus-wrap");
  const focusSelect = form.focus_region_id;
  if (focusWrap) focusWrap.classList.toggle("hidden", scope !== "focus_region_crop");
  if (focusSelect) {
    const previous = focusSelect.value;
    const regions = (datasetData.focus_regions || []).filter(item => item.project_id === projectId && Number(item.enabled) !== 0);
    fillSelect(focusSelect, regions, item => item.id, item => item.name, "选择关注区域");
    if (previous && regions.some(item => item.id === previous)) focusSelect.value = previous;
  }
  renderYoloMapping();
}

function renderDatasetSourceOptions() {
  const projectId = $("#dataset-form select[name=project_id]").value;
  fillMultiSelect($("#dataset-form select[name=frame_set_ids]"), projectFrameSets(projectId), item => item.id, item => `${item.name} (${item.frame_count}帧)`);
  fillMultiSelect($("#dataset-form select[name=history_dataset_ids]"), projectDatasets(projectId), item => item.id, item => `${item.name} (${item.status}) | ${datasetScopeText(item)}`);
  renderFocusExportPanel();
  renderYoloImportOptions();
}

async function refreshDatasets() {
  const data = await loadBootstrap();
  datasetData = data;
  const projectSelect = $("#dataset-form select[name=project_id]");
  const previousProject = projectSelect.value;
  fillSelect(projectSelect, data.projects, item => item.id, item => item.name, "选择产品");
  if (previousProject && data.projects.some(item => item.id === previousProject)) projectSelect.value = previousProject;

  const yoloProjectSelect = $("#yolo-import-form select[name=project_id]");
  const previousYoloProject = yoloProjectSelect?.value;
  if (yoloProjectSelect) {
    fillSelect(yoloProjectSelect, data.projects, item => item.id, item => item.name, "选择产品");
    yoloProjectSelect.value = (previousYoloProject && data.projects.some(item => item.id === previousYoloProject)) ? previousYoloProject : projectSelect.value;
  }

  renderDatasetSourceOptions();
  $("#dataset-list").innerHTML = data.datasets.map(ds => {
    const summary = ds.summary || {};
    return rowHtml(
      esc(ds.name),
      `状态: ${esc(ds.status)} | 视野: ${esc(datasetScopeText(ds))} | ${esc(datasetSummaryText(summary))} | 标签: ${esc(ds.label_codes.join(", "))} | ${esc(ds.output_dir)}`
    );
  }).join("");
}

async function exportDataset(annotatedOnly = false) {
  const form = $("#dataset-form");
  const payload = formToObject(form);
  payload.frame_set_ids = payload.frame_set_ids || [];
  payload.history_dataset_ids = payload.history_dataset_ids || [];
  payload.annotated_only = annotatedOnly;
  window.ActDatasets.FocusExport.collectFocusExportConfig(payload);
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
    showToast("提示：本次未混入历史数据集，请确认不影响旧标签能力", "warn");
  }
  const result = await apiPost("/api/datasets/export", payload);
  const created = result.created ? `，共生成 ${result.created} 个版本` : "";
  showToast((annotatedOnly ? "已标注帧训练数据集已导出" : "训练数据集已导出") + created);
  await refreshDatasets();
}

function renderYoloMapping() {
  const mapping = $("#yolo-import-mapping");
  const summary = $("#yolo-import-summary");
  const form = $("#yolo-import-form");
  if (!mapping || !summary || !form) return;
  if (!yoloInspectResult) {
    summary.textContent = "尚未解析外部数据集。";
    mapping.innerHTML = "";
    return;
  }
  const s = yoloInspectResult.summary || {};
  const errors = (yoloInspectResult.errors || []).length ? ` | 错误: ${yoloInspectResult.errors.length}` : "";
  const warnings = (yoloInspectResult.warnings || []).length ? ` | 警告: ${yoloInspectResult.warnings.length}` : "";
  summary.textContent = `图片: ${s.images || 0} | 标注框: ${s.boxes || 0} | 空标签图片: ${s.empty_label_images || 0} | 缺失标签图片: ${s.missing_label_images || 0}${errors}${warnings}`;
  const labels = projectLabels(form.project_id.value);
  const options = labels.map(label => `<option value="${esc(label.code)}">${esc(label.code)}  ${esc(label.name || label.code)}</option>`).join("");
  mapping.innerHTML = (yoloInspectResult.classes || []).map(item => `
    <div class="row yolo-map-row" data-class-id="${esc(item.class_id)}">
      <div>
        <div class="row-title">外部类别 ${esc(item.class_id)}：${esc(item.name)}</div>
        <div class="row-meta">请选择要映射到的系统标签</div>
      </div>
      <select data-yolo-class="${esc(item.class_id)}">
        <option value="">不导入该类别</option>
        ${options}
      </select>
    </div>
  `).join("");
  $$("[data-yolo-class]", mapping).forEach(select => {
    const suggested = yoloInspectResult.suggested_mapping?.[String(select.dataset.yoloClass)] || "";
    if (suggested && labels.some(label => label.code === suggested)) select.value = suggested;
  });
}

async function inspectYoloDataset() {
  const form = $("#yolo-import-form");
  const payload = formToObject(form);
  if (!payload.project_id) throw new Error("请选择产品");
  if (!payload.dataset_dir) throw new Error("请输入外部 YOLO 数据集目录");
  yoloInspectResult = await apiPost("/api/datasets/import-yolo/inspect", {
    project_id: payload.project_id,
    dataset_dir: payload.dataset_dir,
  });
  renderYoloMapping();
  if ((yoloInspectResult.errors || []).length) {
    showToast(`解析完成，但发现 ${yoloInspectResult.errors.length} 个错误，请检查预览。`, "warn");
  } else {
    showToast("外部 YOLO 数据集解析完成，请确认标签映射。");
  }
}

function collectYoloLabelMapping() {
  const mapping = {};
  $$("[data-yolo-class]", $("#yolo-import-mapping")).forEach(select => {
    if (select.value) mapping[select.dataset.yoloClass] = select.value;
  });
  return mapping;
}

async function importYoloDataset() {
  const form = $("#yolo-import-form");
  const payload = formToObject(form);
  if (!payload.project_id) throw new Error("请选择产品");
  if (!payload.name) throw new Error("请输入数据集名称");
  if (!payload.dataset_dir) throw new Error("请输入外部 YOLO 数据集目录");
  if (!yoloInspectResult || yoloInspectResult.dataset_dir !== payload.dataset_dir) {
    await inspectYoloDataset();
  }
  if ((yoloInspectResult.errors || []).length) {
    throw new Error("外部数据集仍存在格式错误，不能导入");
  }
  payload.label_mapping = collectYoloLabelMapping();
  if (!Object.keys(payload.label_mapping).length) {
    throw new Error("请至少映射一个外部类别");
  }
  if (payload.image_scope === "focus_region_crop" && !payload.focus_region_id) {
    throw new Error("关注区域裁剪数据集必须选择关注区域");
  }
  const dataset = await apiPost("/api/datasets/import-yolo", payload);
  showToast(`外部 YOLO 数据集已导入：${dataset.name}`);
  yoloInspectResult = null;
  renderYoloMapping();
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

$("#dataset-form select[name=project_id]").addEventListener("change", renderDatasetSourceOptions);
$("#dataset-image-scope").addEventListener("change", renderFocusExportPanel);
$("#yolo-import-form select[name=project_id]")?.addEventListener("change", () => {
  yoloInspectResult = null;
  renderYoloImportOptions();
});
$("#yolo-import-scope")?.addEventListener("change", renderYoloImportOptions);
$("#inspect-yolo-dataset")?.addEventListener("click", async () => {
  try {
    await inspectYoloDataset();
  } catch (error) {
    showToast(error.message, "error");
  }
});
$("#yolo-import-form")?.addEventListener("submit", async event => {
  event.preventDefault();
  try {
    await importYoloDataset();
  } catch (error) {
    showToast(error.message, "error");
  }
});

refreshDatasets();
