const form = document.querySelector("#preview-form");
const fileInput = document.querySelector("#pdf-file");
const fileLabel = document.querySelector("#file-label");
const dropZone = document.querySelector("#drop-zone");
const selectedFile = document.querySelector("#selected-file");
const selectedFileName = document.querySelector("#selected-file-name");
const selectedFileDetails = document.querySelector("#selected-file-details");
const submitButton = document.querySelector("#submit-button");
const status = document.querySelector("#status");
const results = document.querySelector("#results");
const resultsTitle = document.querySelector("#results-title");
const pageList = document.querySelector("#page-list");

function formatFileSize(bytes) {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function showFile(file) {
  const hasFile = Boolean(file);
  fileLabel.textContent = hasFile ? "Choose a different PDF" : "Choose a PDF or drop it here";
  dropZone.classList.toggle("has-file", hasFile);
  selectedFile.hidden = !hasFile;
  selectedFileName.textContent = hasFile ? file.name : "";
  selectedFileDetails.textContent = hasFile
    ? `PDF document · ${formatFileSize(file.size)} · One document selected`
    : "";
}

function isPdf(file) {
  return file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
}

function clearPreviousPreview() {
  pageList.replaceChildren();
  results.hidden = true;
}

function selectFile(file) {
  if (!isPdf(file)) {
    fileInput.value = "";
    showFile(null);
    return setStatus("Choose a PDF document.", true);
  }
  showFile(file);
  clearPreviousPreview();
  setStatus(`${file.name} is ready to preview.`);
}

fileInput.addEventListener("change", () => {
  if (fileInput.files.length !== 1) {
    fileInput.value = "";
    showFile(null);
    return setStatus("Upload exactly one PDF document at a time.", true);
  }
  selectFile(fileInput.files[0]);
});

["dragenter", "dragover"].forEach((eventName) => {
  dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropZone.classList.add("dragging");
  });
});

["dragleave", "drop"].forEach((eventName) => {
  dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropZone.classList.remove("dragging");
  });
});

dropZone.addEventListener("drop", (event) => {
  const droppedFiles = event.dataTransfer.files;
  if (droppedFiles.length !== 1) {
    return setStatus("Upload exactly one PDF document at a time.", true);
  }
  const file = droppedFiles[0];
  if (!isPdf(file)) return setStatus("Choose a PDF document.", true);
  const transfer = new DataTransfer();
  transfer.items.add(file);
  fileInput.files = transfer.files;
  selectFile(file);
});

function setStatus(message, isError = false) {
  status.textContent = message;
  status.classList.toggle("error", isError);
}

document.querySelector("#remove-file").addEventListener("click", () => {
  fileInput.value = "";
  showFile(null);
  clearPreviousPreview();
  setStatus("Document removed.");
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const file = fileInput.files[0];
  const inks = [...form.querySelectorAll('input[name="missing_inks"]:checked')];
  if (!file) return setStatus("Choose a PDF first.", true);
  if (!inks.length) return setStatus("Select at least one missing ink color.", true);
  if (file.size > 100 * 1024 * 1024) return setStatus("That PDF is larger than 100 MB.", true);

  const body = new FormData();
  body.append("file", file);
  inks.forEach((input) => body.append("missing_inks", input.value));
  submitButton.disabled = true;
  submitButton.textContent = "Rendering pages…";
  setStatus("Converting the PDF and removing ink channels…");
  results.hidden = true;

  try {
    const response = await fetch("/api/preview", { method: "POST", body });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "The preview could not be created.");
    pageList.replaceChildren();
    const missingLabel = payload.missing_inks
      .map((ink) => ink[0].toUpperCase() + ink.slice(1))
      .join(" + ");
    payload.pages.forEach((page) => {
      const comparison = document.createElement("article");
      comparison.className = "page-comparison";
      const heading = document.createElement("h3");
      heading.textContent = `Page ${page.number}`;
      const grid = document.createElement("div");
      grid.className = "comparison-grid";

      function makePageView(label, source, alt) {
        const figure = document.createElement("figure");
        figure.className = "page-card";
        const viewLabel = document.createElement("figcaption");
        viewLabel.className = "view-label";
        viewLabel.textContent = label;
        const image = document.createElement("img");
        image.src = source;
        image.alt = alt;
        image.width = page.width;
        image.height = page.height;
        const dimensions = document.createElement("span");
        dimensions.className = "dimensions";
        dimensions.textContent = `${page.width} × ${page.height} px`;
        figure.append(viewLabel, image, dimensions);
        return figure;
      }

      grid.append(
        makePageView("Original PDF", page.original_data_url, `Original page ${page.number}`),
        makePageView(`Without ${missingLabel}`, page.data_url, `Simulated page ${page.number}`),
      );
      comparison.append(heading, grid);
      pageList.append(comparison);
    });
    resultsTitle.textContent = `${payload.filename} without ${missingLabel}`;
    results.hidden = false;
    setStatus(`${payload.page_count} page${payload.page_count === 1 ? "" : "s"} rendered.`);
    results.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    setStatus(error.message, true);
  } finally {
    submitButton.disabled = false;
    submitButton.textContent = "Create preview";
  }
});

document.querySelector("#start-over").addEventListener("click", () => {
  form.reset();
  showFile(null);
  clearPreviousPreview();
  setStatus("");
  window.scrollTo({ top: 0, behavior: "smooth" });
});
