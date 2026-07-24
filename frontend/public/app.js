/**
 * app.js — UP Police Data Analyst (frontend)
 *
 * Zero-build vanilla JS:
 * - Calls GET /health on load to gate the question form.
 * - Calls POST /api/query with the question; receives a structured JSON reply.
 * - Renders: answer text, collapsible SQL block, sortable data table,
 *   bar chart (inline SVG), CSV download link, anomaly badges,
 *   suggested follow-ups.
 * - Visible stubs: "CSV Upload" and "PDF Export" buttons are shown but
 *   labelled non-functional (Phase 2 targets).
 */
(function () {
  "use strict";

  // ---------------------------------------------------------------------------
  // DOM refs
  // ---------------------------------------------------------------------------
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => Array.from(document.querySelectorAll(sel));

  const dbStatusEl = $("#db-status");
  const questionInput = $("#question-input");
  const submitBtn = $("#submit-btn");
  const progressSection = $("#progress-section");
  const progressLabel = $("#progress-label");
  const progressFill = $("#progress-fill");
  const stepLabels = $$(".step-labels span");
  const answerSection = $("#answer-section");
  const errorSection = $("#error-section");
  const answerTextEl = $("#answer-text");
  const sqlCodeEl = $("#sql-code");
  const copySqlBtn = $("#copy-sql-btn");
  const tableHeadEl = $("#table-head");
  const tableBodyEl = $("#table-body");
  const tableMetaEl = $("#table-meta");
  const chartContainer = $("#chart-container");
  const csvLinkEl = $("#csv-link");
  const anomaliesSection = $("#anomalies-section");
  const anomalyListEl = $("#anomaly-list");
  const followupsSection = $("#followups-section");
  const followupListEl = $("#followup-list");

  // Mixed rows may contain ints/strings/Date strings for SQL dates; keep as string for table
  // ---------------------------------------------------------------------------
  // Health check
  // ---------------------------------------------------------------------------
  async function checkHealth() {
  try {
    const res = await fetch("/health");
    const payload = await res.json();
    const status = (payload && payload.data && payload.data.status) || "";
    if (res.ok && status === "ok") {
      setDbStatus("Connected ✓", "ok");
      questionInput.disabled = false;
      submitBtn.disabled = false;
    } else if (status === "fallback_sqlite") {
      setDbStatus("Fallback (SQLite) — limited data", "warn");
      questionInput.disabled = false;
      submitBtn.disabled = false;
    } else {
      setDbStatus("Unreachable — contact IT", "error");
    }
  } catch {
    setDbStatus("Unreachable — contact IT", "error");
  }
  }

  function setDbStatus(text, status) {
    dbStatusEl.textContent = text;
    dbStatusEl.className = "db-status " + status;
  }

  // ---------------------------------------------------------------------------
  // Submit
  // ---------------------------------------------------------------------------
  submitBtn.addEventListener("click", onAsk);
  questionInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.ctrlKey && !e.metaKey) {
      e.preventDefault();
      onAsk();
    }
  });

  async function onAsk() {
    const question = questionInput.value.trim();
    if (!question || submitBtn.disabled) return;

    submitBtn.disabled = true;
    hide(answerSection);
    hide(errorSection);
    hide(followupsSection);
    resetProgress();

    try {
      const start = Date.now();
      const res = await fetch("/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
      });

      if (!res.ok) {
        const t = await res.text().catch(() => "");
        showError(
          "Server error (" + res.status + "). Please try again.",
          { code: "http_error", status: res.status, body: t }
        );
        return;
      }

      const data = await res.json();
      // Surface timing
      data._ms = Date.now() - start;
      await onResponse(data);
    } catch (err) {
      showError("Network error — please check your connection and try again.");
    } finally {
      submitBtn.disabled = false;
    }
  }

  async function onResponse(data) {
    // Error path
    if (data.error && !data.rows) {
      showError(data.answer || "Couldn't process that request.", data.error);
      return;
    }

    // Walk steps (best-effort animation)
    const steps = data.steps || [];
    for (let i = 0; i < steps.length; i++) {
      await delay(220);
      setStep(i, steps[i].name, steps[i].status);
    }
    setProgress(Math.min((steps.length / 5) * 100, 100));

    // Answer
    answerTextEl.textContent = data.answer || "(no answer)";
    if (data.sql) {
      sqlCodeEl.textContent = prettySql(data.sql);
    }

    // Table
    if (data.columns && Array.isArray(data.rows)) {
      renderTable(data.columns, data.rows, data.row_count);
    } else {
      clearTable();
    }

    // Chart
    if (data.columns && Array.isArray(data.rows)) {
      renderChart(data.columns, data.rows);
    } else {
      chartContainer.hidden = true;
    }

    // CSV
    if (data.csv_url) {
      csvLinkEl.href = data.csv_url;
      csvLinkEl.style.display = "";
      csvLinkEl.textContent = "⬇ Download CSV";
    } else {
      csvLinkEl.href = "#";
      csvLinkEl.style.display = "none";
    }

    // Anomalies
    if (data.anomalies && data.anomalies.length) {
      anomaliesSection.hidden = false;
      anomalyListEl.innerHTML = data.anomalies
        .map((a) => {
          const sev = (a.severity || "medium").toLowerCase();
          return `<li>
            <strong>${esc(a.label || "Anomaly")}</strong>:
            ${esc(String(a.value ?? "—"))}
            <span class="badge badge-${sev}">${esc(sev)}</span>
          </li>`;
        })
        .join("");
    } else {
      anomaliesSection.hidden = true;
    }

    // Follow-ups
    if (data.followups && data.followups.length) {
      followupsSection.hidden = false;
      followupListEl.innerHTML = data.followups
        .map((q) => `<li><button class="followup-btn" type="button">${esc(q)}</button></li>`)
        .join("");
      followupListEl.querySelectorAll(".followup-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
          questionInput.value = btn.textContent;
          onAsk();
        });
      });
    } else {
      followupsSection.hidden = true;
    }

    show(answerSection);
  }

  // ---------------------------------------------------------------------------
  // Step counter
  // ---------------------------------------------------------------------------
  function resetProgress() {
    progressSection.hidden = false;
    progressFill.style.width = "0%";
    stepLabels.forEach((s, i) => {
      s.className = i === 0 ? "step active" : "step";
    });
  }

  async function setStep(idx, name, status) {
    const labels = stepLabels;
    if (labels[idx]) {
      labels[idx].className = "step " + (status === "done" ? "done" : status === "error" ? "error" : "active");
    }
    const pct = ((idx + 1) / 5) * 100;
    progressFill.style.width = pct + "%";
    progressLabel.textContent = `Step ${idx + 1}/5 — ${(name || "").replace(/_/g, " ")}`;
    await delay(80);
  }

  function setProgress(pct) {
    progressFill.style.width = pct + "%";
  }

  // ---------------------------------------------------------------------------
  // Table
  // ---------------------------------------------------------------------------
  function renderTable(columns, rows, row_count) {
    const shown = Math.min((rows || []).length, 50);
    tableMetaEl.textContent =
      "Showing " + shown + " of " + (row_count || rows.length) + " rows";
    tableHeadEl.innerHTML =
      "<tr>" +
      columns.map((c) => `<th>${esc(String(c))}</th>`).join("") +
      "</tr>";
    tableBodyEl.innerHTML = (rows || [])
      .slice(0, 50)
      .map((row) => {
        return (
          "<tr>" +
          columns
            .map((c) => {
              const v = row == null ? "" : row[c];
              return `<td>${esc(v == null ? "" : String(v))}</td>`;
            })
            .join("") +
          "</tr>"
        );
      })
      .join("");
  }

  function clearTable() {
    tableHeadEl.innerHTML = "";
    tableBodyEl.innerHTML = "";
    tableMetaEl.textContent = "";
  }

  // ---------------------------------------------------------------------------
  // Chart (inline SVG — no external dependencies)
  // ---------------------------------------------------------------------------
  function renderChart(columns, rows) {
    try {
      const labelCol = getLabelCol(columns, rows);
      const numericCols = columns.filter((c, i) => i > 0 && typeof (rows[0] || {})[c] === "number");
      if (numericCols.length === 0 || !rows.length) {
        chartContainer.hidden = true;
        return;
      }
      const valCol = numericCols[0];
      const values = rows.slice(0, 20).map((r) => Number(r?.[valCol]) || 0);
      const labels = rows.slice(0, 20).map((r) => String(r?.[labelCol] ?? ""));
      const max = Math.max(...values, 1);
      const barH = 22;
      const gap = 6;
      const padLeft = 140;
      const chartW = 620;
      const height = labels.length * (barH + gap) + 40;

      const bars = values
        .map((v, i) => {
          const barW = Math.max((v / max) * (chartW - padLeft - 100), 2);
          const y = 30 + i * (barH + gap);
          const labelText = labels[i] || "";
          return (
            `<text x="0" y="${y + barH - 4}" font-family="monospace" font-size="11" fill="#333">${esc(labelText)}</text>` +
            `<rect x="${padLeft}" y="${y}" width="${barW}" height="${barH}" fill="#1d4ed8" rx="2"/>` +
            `<text x="${padLeft + barW + 6}" y="${y + barH - 4}" font-family="monospace" font-size="11" fill="#333">${esc(String(v))}</text>`
          );
        })
        .join("");

      const svg =
        `<svg xmlns="http://www.w3.org/2000/svg" width="${chartW}" height="${height}" viewBox="0 0 ${chartW} ${height}">` +
        bars +
        `</svg>`;
      chartContainer.innerHTML = svg;

      // degrade gracefully if chart container was hidden before
      chartContainer.hidden = false;
    } catch (e) {
      chartContainer.hidden = true;
    }
  }

  function getLabelCol(columns, rows) {
    const first = rows[0] || {};
    const nonNumeric = columns.filter((c, i) => i === 0 || typeof first[c] !== "number");
    return nonNumeric[0] || columns[0];
  }

  // ---------------------------------------------------------------------------
  // Misc helpers
  // ---------------------------------------------------------------------------
  function show(el) { el.hidden = false; }
  function hide(el) { el.hidden = true; }
  function delay(ms) { return new Promise((r) => setTimeout(r, ms)); }
  function esc(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function prettySql(raw) {
    // Lightweight pretty-printer so SQL doesn't turn into a single blob.
    const keywords = /\b(SELECT|FROM|WHERE|AND|OR|JOIN|LEFT|RIGHT|INNER|ON|GROUP BY|ORDER BY|HAVING|LIMIT|OFFSET|AS|CASE|WHEN|THEN|ELSE|END|IN|NOT|NULL|IS|BETWEEN|LIKE|DISTINCT|COUNT|SUM|AVG|MIN|MAX|OVER|PARTITION BY)\b/ig;
    return String(raw)
      .replace(keywords, (m) => m.toUpperCase())
      .replace(/\s+/g, " ")
      .trim();
  }

  copySqlBtn.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(sqlCodeEl.textContent || "");
      const prev = copySqlBtn.textContent;
      copySqlBtn.textContent = "Copied!";
      setTimeout(() => { copySqlBtn.textContent = prev; }, 1500);
    } catch {
      const range = document.createRange();
      range.selectNodeContents(sqlCodeEl);
      const sel = window.getSelection();
      sel.removeAllRanges();
      sel.addRange(range);
    }
  });

  // ---------------------------------------------------------------------------
  // CSV Upload (Phase 2)
  // ---------------------------------------------------------------------------
  const fileInput = document.getElementById("csv-file-input");
  const uploadBtn = document.getElementById("upload-btn");
  const uploadStatus = document.getElementById("upload-status");
  const uploadMessage = document.getElementById("upload-message");
  const uploadMeta = document.getElementById("upload-meta");

  if (fileInput && uploadBtn) {
    fileInput.addEventListener("change", () => {
      uploadBtn.disabled = !fileInput.files?.length;
    });

    uploadBtn.addEventListener("click", async () => {
      const file = fileInput.files?.[0];
      if (!file) return;

      uploadBtn.disabled = true;
      uploadStatus.hidden = false;
      uploadMessage.textContent = "Uploading…";
      uploadMeta.textContent = "";

      try {
        const fd = new FormData();
        fd.append("file", file);
        const res = await fetch("/upload-csv", {
          method: "POST",
          body: fd,
        });
        const data = await res.json();
        if (!res.ok || data.error) {
          throw new Error(data.detail || data.error || "Upload failed.");
        }
        uploadMessage.textContent = data.message || "Upload complete.";
        uploadMeta.textContent = `Table: ${data.table_name}\nRows: ${data.row_count}\nColumns: ${(data.columns || []).join(", ")}`;
      } catch (err) {
        uploadMessage.textContent = err.message || "Upload error.";
      } finally {
        uploadBtn.disabled = true;
      }
    });
  }

  // ---------------------------------------------------------------------------
  // Boot
  // ---------------------------------------------------------------------------
  checkHealth();
  })();
