(function () {
  const namespace = window.ActDatasets = window.ActDatasets || {};

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

  namespace.FocusExport = { collectFocusExportConfig };
})();
