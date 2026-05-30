(function () {
  window.ActDatasets = window.ActDatasets || {};
  const scripts = [
    "/static/js/datasets/state.js",
    "/static/js/datasets/focus_export.js",
    "/static/js/datasets/runtime.js",
  ];

  function load(index) {
    if (index >= scripts.length) return;
    const script = document.createElement("script");
    script.async = false;
    script.src = `${scripts[index]}?v=1.2.0.0`;
    script.onload = () => load(index + 1);
    script.onerror = () => showToast(`数据集模块加载失败：${scripts[index]}`, "error");
    document.head.appendChild(script);
  }

  load(0);
})();
