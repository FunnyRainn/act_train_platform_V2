let videoData = null;
let frameSetNameTouched = false;

function activeProjectId() {
  return $("#active-project").value;
}

function selectedVideo() {
  const videoId = $("#extract-video").value;
  return (videoData?.videos || []).find(video => video.id === videoId);
}

function defaultFrameSetName() {
  const video = selectedVideo();
  const sample = Number($("#sample-n").value || 5);
  return video ? `${video.name}-抽帧${sample}` : "";
}

function syncProjectSelects() {
  const id = activeProjectId();
  $$("form select[name=project_id]").forEach(select => {
    select.value = id;
  });
}

function syncFrameSetName(force = false) {
  const input = $("#frame-set-name");
  if (!input) return;
  if (force || !frameSetNameTouched || !input.value.trim()) {
    input.value = defaultFrameSetName();
    frameSetNameTouched = false;
  }
}

function renderVideoLists() {
  const projectId = activeProjectId();
  const productVideos = videoData.videos.filter(video => !projectId || video.project_id === projectId);
  $("#asset-list").innerHTML = videoData.video_assets.length ? videoData.video_assets.map(asset => rowHtml(
    esc(asset.name),
    `素材来源: ${esc(asset.source_type)} | ${asset.width}x${asset.height} | ${Number(asset.duration_sec).toFixed(1)}秒 | ${esc(asset.stored_path)}`
  )).join("") : `<div class="empty-state">暂无可用素材。刷新时已自动隐藏磁盘文件缺失的素材。</div>`;
  $("#video-list").innerHTML = productVideos.length ? productVideos.map(video => rowHtml(
    esc(video.name),
    `产品: ${esc(video.project_id)} | ${video.width}x${video.height} | ${Number(video.duration_sec).toFixed(1)}秒 | ${esc(video.path)}`
  )).join("") : `<div class="empty-state">暂无可用产品视频。刷新时已自动隐藏磁盘文件缺失的视频。</div>`;
  const frameSets = videoData.frame_sets.filter(fs => !projectId || fs.project_id === projectId);
  $("#frame-set-list").innerHTML = frameSets.length ? frameSets.map(fs => rowHtml(
    esc(fs.name),
    `状态: ${esc(fs.status)} | 帧数: ${fs.frame_count} | 间隔: ${fs.sample_every_n_frames} | ${esc(fs.output_dir)}`,
    `<button data-delete-frame-set="${esc(fs.id)}">删除</button>`
  )).join("") : `<div class="empty-state">暂无可用帧集。刷新时已自动隐藏磁盘目录或图片缺失的帧集。</div>`;
  fillSelect($("#extract-video"), productVideos, item => item.id, item => `${item.name} (${item.width}x${item.height})`, "选择当前产品视频");
  syncFrameSetName(true);
  bindFrameSetDeleteButtons();
}

async function refreshVideos() {
  videoData = await loadBootstrap();
  const currentProject = activeProjectId();
  fillSelect($("#active-project"), videoData.projects, item => item.id, item => item.name, "选择产品");
  if (currentProject) $("#active-project").value = currentProject;
  $$("form select[name=project_id]").forEach(select => fillSelect(select, videoData.projects, item => item.id, item => item.name, "选择产品"));
  renderVideoLists();
}

function bindFrameSetDeleteButtons() {
  $$("[data-delete-frame-set]").forEach(button => {
    button.onclick = async () => {
      const frameSet = videoData.frame_sets.find(item => item.id === button.dataset.deleteFrameSet);
      if (!frameSet) return;
      if (!confirm(`确定删除帧集「${frameSet.name}」吗？这会删除抽帧图片和该帧集上的标注，不影响原始视频和素材库。`)) return;
      try {
        const res = await fetch(`/api/frame-sets/${encodeURIComponent(frameSet.id)}`, { method: "DELETE" });
        await parseApiResponse(res);
        showToast("帧集已删除");
        await refreshVideos();
      } catch (error) {
        showToast(error.message, "error");
      }
    };
  });
}

$("#active-project").addEventListener("change", () => {
  syncProjectSelects();
  frameSetNameTouched = false;
  renderVideoLists();
});

$("#import-mode").addEventListener("change", event => {
  $("#upload-form").classList.toggle("hidden", event.target.value !== "upload");
  $("#import-form").classList.toggle("hidden", event.target.value !== "path");
  syncProjectSelects();
});

$("#frame-set-name")?.addEventListener("input", () => {
  frameSetNameTouched = true;
});

$("#extract-video")?.addEventListener("change", () => syncFrameSetName(true));
$("#sample-n")?.addEventListener("input", () => syncFrameSetName(false));

$("#upload-form").addEventListener("submit", async event => {
  event.preventDefault();
  const form = event.currentTarget;
  syncProjectSelects();
  const projectId = form.querySelector("select[name=project_id]")?.value;
  const fileInput = form.querySelector("input[name=file]");
  if (!projectId) {
    showToast("请先选择产品", "error");
    return;
  }
  if (!fileInput?.files?.length) {
    showToast("请先选择要上传的视频文件", "error");
    return;
  }
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
  const projectId = form.querySelector("select[name=project_id]")?.value;
  const path = form.querySelector("input[name=path]")?.value.trim();
  if (!projectId) {
    showToast("请先选择产品", "error");
    return;
  }
  if (!path) {
    showToast("请填写服务器本地视频路径", "error");
    return;
  }
  try {
    await apiPost("/api/videos/import", formToObject(form));
    showToast("视频已导入素材库并复制到当前产品");
    form.reset();
    await refreshVideos();
  } catch (error) {
    showToast(error.message, "error");
  }
});

async function extractFrames(overwrite = false) {
  return apiPost("/api/frame-sets/extract", {
    video_id: $("#extract-video").value,
    name: $("#frame-set-name").value.trim() || defaultFrameSetName(),
    sample_every_n_frames: Number($("#sample-n").value),
    max_frames: Number($("#max-frames").value),
    overwrite,
  });
}

$("#extract-btn").addEventListener("click", async () => {
  try {
    if (!$("#extract-video").value) throw new Error("请先选择当前产品视频");
    if (!($("#frame-set-name").value.trim() || defaultFrameSetName())) throw new Error("请填写帧集名称");
    await extractFrames(false);
    showToast("抽帧完成");
    frameSetNameTouched = false;
    await refreshVideos();
  } catch (error) {
    if (String(error.message || "").includes("帧集名称已存在")) {
      const overwrite = confirm(`${error.message}\n\n选择“确定”会覆盖原同名帧集，删除旧抽帧图片和旧标注；选择“取消”后请修改帧集名称。`);
      if (!overwrite) return;
      try {
        await extractFrames(true);
        showToast("同名帧集已覆盖并重新抽帧");
        frameSetNameTouched = false;
        await refreshVideos();
      } catch (overwriteError) {
        showToast(overwriteError.message, "error");
      }
      return;
    }
    showToast(error.message, "error");
  }
});

refreshVideos();
