async function refreshLabels() {
  const labels = await apiGet("/api/labels");
  $("#label-list").innerHTML = labels.map(label => rowHtml(
    `${esc(label.code)} ${esc(label.name)} ${label.enabled ? "" : "（停用）"}`,
    `类型: ${esc(label.group_code)} | 框选说明: ${esc(label.box_instruction || "未填写")}`,
    `<button data-code="${esc(label.code)}">编辑</button>`
  )).join("");
  $$("#label-list button").forEach(btn => {
    btn.onclick = () => {
      const label = labels.find(item => item.code === btn.dataset.code);
      const form = $("#label-form");
      form.code.value = label.code;
      form.name.value = label.name;
      form.description.value = label.description;
      form.box_instruction.value = label.box_instruction;
      form.enabled.checked = !!label.enabled;
    };
  });
}

$("#label-form").addEventListener("submit", async event => {
  event.preventDefault();
  const form = event.currentTarget;
  try {
    await apiPost("/api/labels", formToObject(form));
    form.reset();
    form.enabled.checked = true;
    showToast("标签已保存");
    await refreshLabels();
  } catch (error) {
    showToast(error.message, "error");
  }
});

refreshLabels();
