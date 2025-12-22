(() => {
  document.addEventListener("input", (ev) => {
    const el = ev.target;
    if (el && el.name && el.name.endsWith("[sets]")) {
      const v = Number(el.value || 0);
      if (v < 0) el.value = 0;
      if (v > 99) el.value = 99;
    }
  });
})();
