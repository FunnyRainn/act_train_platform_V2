async function refreshPackages() {
  const data = await loadBootstrap();
  const params = new URLSearchParams(location.search);
  const focusJob = params.get("train_job_id");
  const packages = data.packages || [];
  $("#package-list").innerHTML = packages.length ? packages.map(pkg => {
    const focus = pkg.train_job_id === focusJob ? " selected" : "";
    const meta = pkg.metadata || {};
    const labels = (meta.label_codes || []).join(", ") || "-";
    return `<div class="row${focus}">
      <div>
        <div class="row-title">${esc(pkg.name)}</div>
        <div class="row-meta">
          状态: ${esc(pkg.status)} | 来源训练任务: ${esc(pkg.train_job_id)} | 标签: ${esc(labels)}<br>
          模型目录: ${esc(pkg.package_dir)}
        </div>
      </div>
      <div>
        ${focus ? '<span class="badge-soft">当前查看</span>' : ''}
      </div>
    </div>`;
  }).join("") : `<div class="empty-state">暂无模型。训练完成或停止后，若已有可用模型文件，系统会自动整理到这里。</div>`;
}

refreshPackages();
