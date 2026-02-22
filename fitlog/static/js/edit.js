/**
 * edit.js ist verantwortlich für die Bearbeitungsseite vom Trainingsplan (edit.html).
 *
 * Funktionen:
 * - Drag und drop zum Ändern der Reihenfolge der Übungen
 * - Entfernen einzelner Übungen
 * - "Übung hinzufügen" speichert erst den Plan, dann fügt es die Übung hinzu
 */

(() => {
  const table = document.getElementById("dndTable");
  const tbody = document.querySelector("#dndTable tbody");
  if (!table || !tbody) return;

  const removeUrl = table.dataset.removeUrl; // kommt aus data-remove-url im HTML
  let dragEl = null;

  // Aktualisiert die versteckten position[] Felder.
  function updatePositions() {
    [...tbody.querySelectorAll("tr.dnd-row")].forEach((tr, i) => {
      const pos = tr.querySelector('input[name="position[]"]');
      if (pos) pos.value = i + 1;
    });
  }

  // Ermittelt das Element, VOR dem die gezogene Zeile eingefügt werden soll.
  // Vergleicht die Position der Maus mit der Mitte jeder Zeile und wählt die nächstgelegene unterhalb des Cursors.
  function getDragAfterElement(container, y) {
    const els = [...container.querySelectorAll("tr.dnd-row:not(.is-dragging)")];
    return els.reduce(
      (closest, child) => {
        const box = child.getBoundingClientRect();
        const offset = y - box.top - box.height / 2;
        if (offset < 0 && offset > closest.offset) return { offset, element: child };
        return closest;
      },
      { offset: Number.NEGATIVE_INFINITY }
    ).element;
  }

  // Drag und drop Events
  tbody.addEventListener("dragstart", (e) => {
    const row = e.target.closest("tr.dnd-row");
    if (!row) return;
    dragEl = row;
    row.classList.add("is-dragging");
  });

  // Nach dem Loslassen Positionen neu nummerieren
  tbody.addEventListener("dragend", () => {
    if (dragEl) dragEl.classList.remove("is-dragging");
    dragEl = null;
    updatePositions();
  });

  // Während des Ziehens wird Zeile an neue Position verschoben
  tbody.addEventListener("dragover", (e) => {
    e.preventDefault();
    const after = getDragAfterElement(tbody, e.clientY);
    const dragging = tbody.querySelector("tr.dnd-row.is-dragging");
    if (!dragging) return;

    if (after == null) tbody.appendChild(dragging);
    else tbody.insertBefore(dragging, after);
  });

  // Übung entfernen mit dem x-Button
  tbody.addEventListener("click", async (e) => {
    const btn = e.target.closest("[data-remove]");
    if (!btn) return;

    if (!removeUrl) {
      alert("remove URL fehlt (data-remove-url).");
      return;
    }

    const exId = btn.getAttribute("data-remove");
    if (!confirm("Übung aus dem Plan entfernen?")) return;

    const res = await fetch(removeUrl, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ exercise_id: exId }),
    });

    if (res.ok) location.reload();
    else alert("Entfernen fehlgeschlagen.");
  });

  // Beim "Übung hinzufügen" erst Plan speichern, dann Übung hinzufügen
  const editForm = document.getElementById("edit-form");
  const addForm = document.querySelector("form.add-exercise-form");

  if (editForm && addForm) {
    addForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      updatePositions();

      const addBtn = addForm.querySelector('button[type="submit"]');
      if (addBtn) addBtn.disabled = true;

      try {
        // Schritt 1: Aktuelle Änderungen am Plan speichern
        const saveRes = await fetch(editForm.action, {
          method: "POST",
          body: new FormData(editForm),
        });
        if (!saveRes.ok) {
          alert("Konnte Änderungen nicht speichern. Bitte zuerst speichern, dann Übung hinzufügen.");
          return;
        }

        // Schritt 2: Neue Übung zum Plan hinzufügen
        const addRes = await fetch(addForm.action, {
          method: "POST",
          body: new FormData(addForm),
        });
        if (!addRes.ok) {
          alert("Übung konnte nicht hinzugefügt werden.");
          return;
        }

        location.reload();
      } catch (err) {
        alert("Netzwerkfehler. Bitte erneut versuchen.");
      } finally {
        if (addBtn) addBtn.disabled = false;
      }
    });
  }
  // Positionen initial setzen, wenn die Seite z.B. neu geladen wird
  updatePositions();
})();
