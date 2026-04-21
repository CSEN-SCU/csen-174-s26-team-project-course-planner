function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else node.setAttribute(k, v);
  }
  for (const c of children) node.appendChild(c);
  return node;
}

function renderRecommendations(recs) {
  const root = document.getElementById("results");
  root.innerHTML = "";

  if (!recs.length) {
    root.appendChild(
      el("div", {
        class: "muted",
        text:
          "No results. You may have already completed everything in this term’s catalog, or the term doesn’t match the catalog export.",
      })
    );
    return;
  }

  for (const r of recs) {
    const c = r.course;
    const rationale = r.rationale || {};
    const bullets = rationale.ai_bullets || rationale.notes || [];

    const title = el("div", { class: "recTitle" }, [
      el("strong", { text: `${c.code} — ${c.title}` }),
      el("div", { class: "score", text: `score ${Number(r.score).toFixed(2)}` }),
    ]);

    const status = c.status === "eligible" ? "Eligible (demo rules)" : "Prereqs not met (demo rules)";
    const meta = el("div", { class: "meta" }, [
      document.createTextNode(`${c.term} · ${c.units} units · ${c.schedule} · ${status}`),
    ]);

    const inst =
      c.instructors && c.instructors.length
        ? el("div", { class: "muted", text: `Instructors (ranked): ${c.instructors.slice(0, 4).join(" / ")}` })
        : el("div", { class: "muted", text: "" });

    const ul = el("ul", { class: "bullets" });
    for (const b of bullets) ul.appendChild(el("li", { text: String(b) }));

    const card = el("div", { class: "recCard" }, [title, meta, inst, ul]);
    root.appendChild(card);
  }
}

function renderProgressPlan(data) {
  const parsedEl = document.getElementById("parsed");
  const resultsEl = document.getElementById("results");
  if (parsedEl) {
    parsedEl.textContent = JSON.stringify(
      {
        completed_codes: data.completed_codes,
        missing_major_codes: data.missing_major_codes,
        unsatisfied_requirements: data.unsatisfied_requirements,
      },
      null,
      2
    );
  }
  if (!resultsEl) return;
  resultsEl.innerHTML = "";
  const recs = data.recommendations || [];
  if (!recs.length) {
    resultsEl.appendChild(
      el("div", {
        class: "muted",
        text: "No selectable courses found. You may have satisfied major/core requirements, or the catalog export is missing matching courses.",
      })
    );
    return;
  }
  for (const r of recs) {
    const title = el("div", { class: "recTitle" }, [
      el("strong", { text: `${r.code} — ${r.title}` }),
      el("div", { class: "score", text: r.why }),
    ]);
    const meta = el("div", { class: "meta" }, [
      document.createTextNode(`${r.term} · ${r.units} units · ${r.schedule || "TBA"}`),
    ]);
    const inst =
      r.instructors && r.instructors.length
        ? el("div", { class: "muted", text: `Instructors (ranked): ${r.instructors.slice(0, 4).join(" / ")}` })
        : el("div", { class: "muted", text: "" });
    const tagLine = r.tags ? el("div", { class: "muted", text: `tags: ${r.tags}` }) : el("div", { class: "muted", text: "" });
    const card = el("div", { class: "recCard" }, [title, meta, inst, tagLine]);
    resultsEl.appendChild(card);
  }
}

// Transcript-based submit flow removed (Academic Progress only).

document.getElementById("progressBtn")?.addEventListener("click", async () => {
  const form = document.getElementById("planForm");
  const fd = new FormData(form);
  const file = fd.get("progress_file");
  const majorUrl = String(fd.get("major_requirements_url") || "").trim();
  const term = String(fd.get("term") || "").trim() || "2026 Spring";
  const majorReqsEl = document.getElementById("majorReqs");
  if (!file || !(file instanceof File) || !file.name.toLowerCase().endsWith(".xlsx")) {
    if (majorReqsEl) majorReqsEl.textContent = "Please select an Academic Progress .xlsx file first.";
    return;
  }
  if (!majorUrl) {
    if (majorReqsEl) majorReqsEl.textContent = "Please provide a public major requirements URL first.";
    return;
  }
  document.getElementById("parsed").textContent = "Generating…";
  document.getElementById("results").textContent = "Generating…";
  if (majorReqsEl) majorReqsEl.textContent = "Fetching…";

  // 1) Upload progress file
  const up = new FormData();
  up.append("file", file);
  const upResp = await fetch("/api/upload_progress", { method: "POST", body: up });
  if (!upResp.ok) {
    document.getElementById("parsed").textContent = `Upload failed: ${upResp.status}\n${await upResp.text()}`;
    document.getElementById("results").textContent = "";
    return;
  }
  const upData = await upResp.json();
  const fileId = upData.file_id;
  if (!fileId) {
    document.getElementById("parsed").textContent = `Upload failed: missing file_id\n${JSON.stringify(upData)}`;
    document.getElementById("results").textContent = "";
    return;
  }

  const mrResp = await fetch(`/api/major_requirements?url=${encodeURIComponent(majorUrl)}`);
  if (majorReqsEl) {
    majorReqsEl.textContent = mrResp.ok
      ? JSON.stringify(await mrResp.json(), null, 2)
      : `Fetch failed: ${mrResp.status}\n${await mrResp.text()}`;
  }

  const resp = await fetch(
    `/api/plan_from_progress?url=${encodeURIComponent(majorUrl)}&term=${encodeURIComponent(term)}&file_id=${encodeURIComponent(
      fileId
    )}`
  );
  if (!resp.ok) {
    const t = await resp.text();
    document.getElementById("parsed").textContent = `Request failed: ${resp.status}\n${t}`;
    document.getElementById("results").textContent = "";
    return;
  }
  const data = await resp.json();
  renderProgressPlan(data);
});
