let selectedLabels = new Set();
let labelsCache = [];

function renderLabelCards() {
  const groups = ["A", "B", "C"];
  $("#label-card-list").innerHTML = groups.map(group => {
    const labels = labelsCache.filter(label => label.group_code === group && label.enabled);
    if (!labels.length) return "";
    return `
      <div class="label-group">
        <div class="row-title">${group} 类标签</div>
        <div class="label-card-list">
          ${labels.map(label => `
            <div class="label-card ${selectedLabels.has(label.code) ? "selected" : ""}" data-code="${esc(label.code)}">
              <strong>${esc(label.code)}</strong> ${esc(label.name)}
              <div class="row-meta">${esc(label.box_instruction || "未填写框选说明")}</div>
            </div>
          `).join("")}
        </div>
      </div>
    `;
  }).join("");
  $$(".label-card").forEach(card => {
    card.onclick = () => {
      const code = card.dataset.code;
      selectedLabels.has(code) ? selectedLabels.delete(code) : selectedLabels.add(code);
      renderLabelCards();
    };
  });
}

async function refreshProjects() {
  const data = await loadBootstrap();
  labelsCache = data.labels;
  renderLabelCards();
  $("#project-list").innerHTML = data.projects.map(project => rowHtml(
    esc(project.name),
    `产品: ${esc(project.product_name || "-")} | 流程说明: ${esc(project.sop_name || "-")} | 标签: ${esc(project.label_codes.join(", ") || "-")}`,
    `<button data-id="${esc(project.id)}">编辑</button>`
  )).join("");
  $$("#project-list button").forEach(btn => {
    btn.onclick = () => {
      const project = data.projects.find(item => item.id === btn.dataset.id);
      const form = $("#project-form");
      form.id.value = project.id;
      form.name.value = project.name;
      form.product_name.value = project.product_name;
      form.sop_name.value = project.sop_name;
      form.station_name.value = project.station_name;
      form.notes.value = project.notes;
      selectedLabels = new Set(project.label_codes);
      renderLabelCards();
    };
  });
}

$("#project-form").addEventListener("submit", async event => {
  event.preventDefault();
  const form = event.currentTarget;
  try {
    const payload = formToObject(form);
    payload.label_codes = Array.from(selectedLabels);
    await apiPost("/api/projects", payload);
    form.reset();
    selectedLabels.clear();
    renderLabelCards();
    showToast("产品配置已保存");
    await refreshProjects();
  } catch (error) {
    showToast(error.message, "error");
  }
});

refreshProjects();
