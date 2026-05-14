async function refreshVideos() {
  const data = await loadBootstrap();
  $$("select[name=project_id]").forEach(select => fillSelect(select, data.projects, item => item.id, item => item.name, "选择项目"));
  fillSelect($("#extract-video"), data.videos, item => item.id, item => `${item.name} (${item.width}x${item.height})`, "选择视频");
  $("#video-list").innerHTML = data.videos.map(video => rowHtml(
    esc(video.name),
    `项目: ${esc(video.project_id)} | ${video.width}x${video.height} | ${Number(video.duration_sec).toFixed(1)}秒 | ${esc(video.path)}`
  )).join("");
  $("#frame-set-list").innerHTML = data.frame_sets.map(fs => rowHtml(
    esc(fs.name),
    `状态: ${esc(fs.status)} | 帧数: ${fs.frame_count} | 间隔: ${fs.sample_every_n_frames} | ${esc(fs.output_dir)}`
  )).join("");
}

$("#upload-form").addEventListener("submit", async event => {
  event.preventDefault();
  const form = event.currentTarget;
  const body = new FormData(form);
  try {
    const res = await fetch("/api/videos/upload", { method: "POST", body });
    await parseApiResponse(res);
    showToast("视频已上传");
    form.reset();
    await refreshVideos();
  } catch (error) {
    showToast(error.message, "error");
  }
});

$("#import-form").addEventListener("submit", async event => {
  event.preventDefault();
  try {
    await apiPost("/api/videos/import", formToObject(event.currentTarget));
    showToast("视频已导入");
    event.currentTarget.reset();
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
