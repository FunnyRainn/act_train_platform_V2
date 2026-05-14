let videoData = null;

function activeProjectId() {
  return $("#active-project").value;
}

function syncProjectSelects() {
  const id = activeProjectId();
  $$("form select[name=project_id]").forEach(select => {
    select.value = id;
  });
}

function renderVideoLists() {
  const projectId = activeProjectId();
  const productVideos = videoData.videos.filter(video => !projectId || video.project_id === projectId);
  $("#asset-list").innerHTML = videoData.video_assets.map(asset => rowHtml(
    esc(asset.name),
    `素材来源: ${esc(asset.source_type)} | ${asset.width}x${asset.height} | ${Number(asset.duration_sec).toFixed(1)}秒 | ${esc(asset.stored_path)}`
  )).join("");
  $("#video-list").innerHTML = productVideos.map(video => rowHtml(
    esc(video.name),
    `产品: ${esc(video.project_id)} | ${video.width}x${video.height} | ${Number(video.duration_sec).toFixed(1)}秒 | ${esc(video.path)}`
  )).join("");
  const frameSets = videoData.frame_sets.filter(fs => !projectId || fs.project_id === projectId);
  $("#frame-set-list").innerHTML = frameSets.map(fs => rowHtml(
    esc(fs.name),
    `状态: ${esc(fs.status)} | 帧数: ${fs.frame_count} | 间隔: ${fs.sample_every_n_frames} | ${esc(fs.output_dir)}`
  )).join("");
  fillSelect($("#extract-video"), productVideos, item => item.id, item => `${item.name} (${item.width}x${item.height})`, "选择当前产品视频");
}

async function refreshVideos() {
  videoData = await loadBootstrap();
  fillSelect($("#active-project"), videoData.projects, item => item.id, item => item.name, "选择产品");
  $$("form select[name=project_id]").forEach(select => fillSelect(select, videoData.projects, item => item.id, item => item.name, "选择产品"));
  renderVideoLists();
}

$("#active-project").addEventListener("change", () => {
  syncProjectSelects();
  renderVideoLists();
});

$("#import-mode").addEventListener("change", event => {
  $("#upload-form").classList.toggle("hidden", event.target.value !== "upload");
  $("#import-form").classList.toggle("hidden", event.target.value !== "path");
  syncProjectSelects();
});

$("#upload-form").addEventListener("submit", async event => {
  event.preventDefault();
  const form = event.currentTarget;
  syncProjectSelects();
  const body = new FormData(form);
  try {
    const res = await fetch("/api/videos/upload", { method: "POST", body });
    await parseApiResponse(res);
    showToast("视频已进入素材库并复制到当前产品");
    form.reset();
    await refreshVideos();
  } catch (error) {
    showToast(error.message, "error");
  }
});

$("#import-form").addEventListener("submit", async event => {
  event.preventDefault();
  const form = event.currentTarget;
  syncProjectSelects();
  try {
    await apiPost("/api/videos/import", formToObject(form));
    showToast("视频已导入素材库并复制到当前产品");
    form.reset();
    await refreshVideos();
  } catch (error) {
    showToast(error.message, "error");
  }
});

$("#extract-btn").addEventListener("click", async () => {
  try {
    await apiPost("/api/frame-sets/extract", {
      video_id: $("#extract-video").value,
      sample_every_n_frames: Number($("#sample-n").value),
      max_frames: Number($("#max-frames").value),
    });
    showToast("抽帧完成");
    await refreshVideos();
  } catch (error) {
    showToast(error.message, "error");
  }
});

refreshVideos();
