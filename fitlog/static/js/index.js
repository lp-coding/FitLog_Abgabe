( () => {
  const list = document.getElementById("planList");
  const btnRecord = document.getElementById("btnRecord");
  const btnProgress = document.getElementById("btnProgress");
  const btnEdit = document.getElementById("btnEdit");
  const btnDelete = document.getElementById("btnDelete");
  const btnAdd = document.getElementById("btnAdd");

  const selId = () => (list && list.value ? list.value : null);

  function updateRecordButton() {
    if (!btnRecord) return;
    const hasSel = !!selId();
    btnRecord.disabled = !hasSel;
  }

  updateRecordButton();

  if (list) list.addEventListener("change", updateRecordButton);

  // Erfassen starten -> /sessions/new?plan_id=<id>
  if (btnRecord) {
    btnRecord.addEventListener("click", () => {
      const id = selId();
      if (!id) return;
      const baseUrl = btnRecord.dataset.newSessionUrl;
      if (!baseUrl) return;
      window.location.href = baseUrl + "?plan_id=" + encodeURIComponent(id);
    });
  }

  // Trainingsfortschritt -> Overview
  if (btnProgress) {
    btnProgress.addEventListener("click", () => {
      const url = btnProgress.dataset.progressUrl;
      if (url) window.location.href = url;
    });
  }

  // Bearbeiten -> /plans/<id>/edit
  if (btnEdit) {
    btnEdit.addEventListener("click", () => {
      const id = selId();
      if (!id) return alert("Bitte einen Plan in der Liste auswählen.");

      const tmpl = btnEdit.dataset.editTemplate; // enthält .../0/edit
      if (!tmpl) return;
      window.location.href = tmpl.replace("0", id);
    });
  }

  // Löschen (Soft-Delete) -> POST /plans/<id>/delete
  if (btnDelete) {
    btnDelete.addEventListener("click", async () => {
      const id = selId();
      if (!id) return alert("Bitte einen Plan in der Liste auswählen.");
      if (!confirm("Diesen Plan wirklich löschen?")) return;

      try {
        const res = await fetch(`/plans/${id}/delete`, { method: "POST" });
        if (res.ok) location.reload();
        else alert("Löschen fehlgeschlagen.");
      } catch {
        alert("Netzwerkfehler beim Löschen.");
      }
    });
  }

  // Hinzufügen -> Prompt -> POST /plans/create
  if (btnAdd) {
    btnAdd.addEventListener("click", async () => {
      const name = (prompt("Name des neuen Plans:") || "").trim();
      if (!name) return;

      const createUrl = btnAdd.dataset.createUrl;
      const nextUrl = btnAdd.dataset.nextUrl;

      if (!createUrl) return;

      try {
        const form = new URLSearchParams({ name, next: nextUrl || "" });
        const res = await fetch(createUrl, {
          method: "POST",
          headers: { "Content-Type": "application/x-www-form-urlencoded" },
          body: form.toString(),
        });
        if (res.redirected) window.location.href = res.url;
        else location.reload();
      } catch {
        alert("Anlegen fehlgeschlagen.");
      }
    });
  }
})();
