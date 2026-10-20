import { esc, publicPath, fileUrl, fileMirrorUrl, isExternalFile, fileName, downloadName, sizeLabel, inputStage } from "./records.mjs";

export const roleNames = { pp: "Pseudopotential", nao: "Physical NAO", abf: "Auxiliary basis", for_aux: "Orbital for ABF generation", species_defaults: "FHI-aims species defaults", generation_evidence: "Generation evidence" };
const previewable = path => !/\.(?:png|jpe?g|webp|gif|pdf|zip|gz|xz|tar|bin)$/i.test(path);

export function renderFiles(files, { input = false } = {}) {
  if (!files.length) return '<p class="empty-panel">No files listed in this group.</p>';
  return `<div class="file-list">${files.map(file => {
    const url = fileUrl(file);
    if (!url) return '<div class="notice warning">File link unavailable.</div>';
    const mirror = fileMirrorUrl(file);
    const alias = file.name_source === "descriptive_alias";
    const external = isExternalFile(file);
    return `<article class="file-row">
      <div class="file-info"><strong>${esc(fileName(file))}</strong><span>${esc(input ? inputStage(file) : roleNames[file.role] || file.role || "Data file")} <span aria-hidden="true">·</span> ${esc(sizeLabel(file.size_bytes))}</span>
      ${alias ? '<span class="name-note">Descriptive filename</span>' : file.name_source === "calculation_alias" ? '<span class="name-note">Calculation filename</span>' : ""}${external ? '<span class="name-note">External archive · integrity by SHA-256</span>' : ""}
      </div>
      <div class="file-actions">${previewable(file.path) ? `<button type="button" class="text-button" data-preview="${esc(file.path)}" data-preview-url="${esc(url)}" data-name="${esc(fileName(file))}" data-download="${esc(downloadName(file))}">View</button>` : `<a href="${esc(url)}" target="_blank" rel="noopener">Open</a>`}<a class="download-link" href="${esc(url)}" download="${esc(downloadName(file))}">Download <span aria-hidden="true">↓</span></a>${mirror ? `<a class="download-link mirror-link" href="${esc(mirror)}" download="${esc(downloadName(file))}">Mirror <span aria-hidden="true">↗</span></a>` : ""}</div>
    </article>`;
  }).join("")}</div>`;
}

export function installPreview(dialog) {
  let controller;
  document.addEventListener("click", async event => {
    const button = event.target.closest("[data-preview]");
    if (!button) return;
    const url = button.dataset.previewUrl || publicPath(button.dataset.preview);
    if (!url) return;
    controller?.abort();
    controller = new AbortController();
    const current = controller;
    dialog.querySelector("h2").textContent = button.dataset.name;
    dialog.querySelector(".preview-path").textContent = button.dataset.preview;
    const download = dialog.querySelector(".preview-download");
    download.href = url;
    download.download = button.dataset.download;
    const pre = dialog.querySelector("pre");
    const status = dialog.querySelector(".preview-status");
    pre.textContent = "Loading source file…";
    status.textContent = "Read-only preview; the download retains the source bytes.";
    if (!dialog.open) dialog.showModal();
    try {
      const response = await fetch(url, { signal: current.signal });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const reader = response.body.getReader();
      const chunks = [];
      let size = 0;
      let truncated = false;
      const limit = 65536;
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        const remaining = limit - size;
        chunks.push(value.subarray(0, remaining));
        size += Math.min(value.length, remaining);
        if (size >= limit) { truncated = true; await reader.cancel(); break; }
      }
      const bytes = new Uint8Array(size);
      let offset = 0;
      for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.length; }
      if (current.signal.aborted) return;
      pre.textContent = bytes.includes(0) ? "This file appears to be binary. Download it to inspect the original content." : new TextDecoder("utf-8").decode(bytes) || "This source file is empty.";
      if (truncated) status.textContent = "Preview limited to the first 64 KB. Download the complete source file.";
    } catch (error) {
      if (error.name !== "AbortError") { pre.textContent = `Could not read this file (${error.message}).`; status.textContent = "The source file is currently unavailable."; }
    }
  });
  dialog.querySelector(".dialog-close").addEventListener("click", () => dialog.close());
  dialog.addEventListener("close", () => controller?.abort());
  dialog.addEventListener("click", event => { if (event.target === dialog) dialog.close(); });
}
