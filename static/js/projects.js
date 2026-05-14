let labelsCache = [];

async function refreshProjects() {
  const data = await loadBootstrap();
  labelsCache = data.labels;
  fillMultiSelect($("#project-form select[name=label_codes]"), labelsCache, item => item.code, item => `${item.code} ${item.name}`);
  $("#project-list").innerHTML = data.projects.map(project => rowHtml(
    esc(project.name),
    `产品: ${esc(project.product_name || "-")} | SOP: ${esc(project.sop_name || "-")} | 标签: ${esc(project.label_codes.join(", ") || "-")}`,
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
      Array.from(form.label_codes.options).forEach(option => {
        option.selected = project.label_codes.includes(option.value);
      });
    };
  });
}

$("#project-form").addEventListener("submit", async event => {
  event.preventDefault();
  try {
    await apiPost("/api/projects", formToObject(event.currentTarget));
    event.currentTarget.reset();
    showToast("项目已保存");
    await refreshProjects();
  } catch (error) {
    showToast(error.message, "error");
  }
});

refreshProjects();
