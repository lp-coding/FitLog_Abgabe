(() => {
  const page = document.getElementById("progressPage");
  if (!page) return;

  const homeUrl = page.dataset.homeUrl;
  const overviewUrl = page.dataset.overviewUrl;
  const planPngTemplate = page.dataset.planPngTemplate;         // enthält .../0
  const exercisePngTemplate = page.dataset.exercisePngTemplate; // enthält .../0

  function goHome() {
    if (homeUrl) window.location.href = homeUrl;
  }

  const btnBack = document.getElementById("btnBack");
  if (btnBack) btnBack.addEventListener("click", goHome);

  const btnClose = document.getElementById("btnClose");
  if (btnClose) btnClose.addEventListener("click", goHome);

  function navigate(diagramType, planId, exerciseId) {
    if (!overviewUrl) return;

    const params = new URLSearchParams();
    if (diagramType) params.set("diagram_type", diagramType);

    if (diagramType === "plan" && planId) params.set("plan_id", planId);
    else if (diagramType === "exercise" && exerciseId) params.set("exercise_id", exerciseId);

    const query = params.toString();
    window.location.href = query ? `${overviewUrl}?${query}` : overviewUrl;
  }

  const diagramTypeSelect = document.getElementById("diagramType");
  const planSelect = document.getElementById("planSelect");
  const exerciseSelect = document.getElementById("exerciseSelect");

  const planGroup = document.getElementById("planGroup");
  const exerciseGroup = document.getElementById("exerciseGroup");

  if (diagramTypeSelect) {
    diagramTypeSelect.addEventListener("change", function () {
      const type = this.value;

      if (type === "plan") {
        if (planGroup) planGroup.style.display = "";
        if (exerciseGroup) exerciseGroup.style.display = "none";
        navigate("plan", planSelect ? planSelect.value : "", null);
      } else {
        if (planGroup) planGroup.style.display = "none";
        if (exerciseGroup) exerciseGroup.style.display = "";
        navigate("exercise", null, exerciseSelect ? exerciseSelect.value : "");
      }
    });
  }

  if (planSelect) {
    planSelect.addEventListener("change", function () {
      const diagramType = diagramTypeSelect ? diagramTypeSelect.value : "plan";
      navigate(diagramType, this.value, null);
    });
  }

  if (exerciseSelect) {
    exerciseSelect.addEventListener("change", function () {
      const diagramType = diagramTypeSelect ? diagramTypeSelect.value : "exercise";
      navigate(diagramType, null, this.value);
    });
  }

  const btnExport = document.getElementById("btnExport");
  if (btnExport) {
    btnExport.addEventListener("click", function () {
      const diagramType = diagramTypeSelect ? diagramTypeSelect.value : "plan";

      if (diagramType === "plan") {
        const pid = planSelect ? planSelect.value : "";
        if (!pid || !planPngTemplate) return;
        window.location.href = planPngTemplate.replace("0", pid) + "?download=1";
      } else {
        const eid = exerciseSelect ? exerciseSelect.value : "";
        if (!eid || !exercisePngTemplate) return;
        window.location.href = exercisePngTemplate.replace("0", eid) + "?download=1";
      }
    });
  }
})();
