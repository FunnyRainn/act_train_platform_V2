(function () {
  const namespace = window.ActAnnotate = window.ActAnnotate || {};

  function isTypingTarget(target) {
    const tagName = target?.tagName?.toLowerCase();
    return target?.isContentEditable || ["input", "textarea"].includes(tagName);
  }

  function bindFrameShortcuts(actions) {
    document.addEventListener("keydown", event => {
      if (isTypingTarget(event.target)) return;
      if (event.ctrlKey && !event.altKey && !event.metaKey && (event.code === "KeyO" || event.key.toLowerCase() === "o")) {
        event.preventDefault();
        actions.clearCurrentFrameBoxes();
        return;
      }
      if (event.ctrlKey || event.altKey || event.metaKey) return;
      const key = event.key.toLowerCase();
      if (event.code === "KeyA" || key === "a") {
        event.preventDefault();
        actions.goFrame(-1);
      }
      if (event.code === "KeyD" || key === "d") {
        event.preventDefault();
        actions.goFrame(1);
      }
    });
  }

  namespace.Shortcuts = { bindFrameShortcuts };
})();
