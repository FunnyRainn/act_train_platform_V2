(function () {
  window.ActAnnotate = window.ActAnnotate || {};
  const versionQuery = new URL(document.currentScript.src).search;
  const scripts = [
    "/static/js/annotate/state.js",
    "/static/js/annotate/shortcuts.js",
    "/static/js/annotate/runtime.js",
  ];

  function load(index) {
    if (index >= scripts.length) return;
    const script = document.createElement("script");
    script.async = false;
    script.src = `${scripts[index]}${versionQuery}`;
    script.onload = () => load(index + 1);
    script.onerror = () => showToast(`标注模块加载失败：${scripts[index]}`, "error");
    document.head.appendChild(script);
  }

  load(0);
})();
