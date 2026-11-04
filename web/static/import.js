// The outline drop box: choose outline files, preview the deadlines Groot finds,
// check them, then save the ones you tick. Text from the server always goes on
// the page with textContent, so a title found in an outline can never turn into HTML.
import {answer, element, post, show, showOffline} from "./common.js";

// The same limits the server checks. Checking here as well means a wrong
// file is pointed out straight away, before anything is sent.
const MAX_OUTLINES = 8;
const MAX_FILE_BYTES = 10 * 1024 * 1024;

// Plain words for each row's status and where its date came from
const STATUS_TEXT = {
  exact: "Exact date",
  assumed: "Assumed, please check",
  needs_input: "Needs your date",
  unknown: "No date yet",
  past: "Already passed",
};
const SOURCE_TEXT = {
  outline: "From the outline",
  canvas: "From Canvas",
  both: "From the outline and Canvas",
};

const dropZone = document.getElementById("drop-zone");
const outlineInput = document.getElementById("outline-input");
const fileMessage = document.getElementById("file-message");
const outlineList = document.getElementById("outline-list");
const timetableInput = document.getElementById("timetable-input");
const canvasInput = document.getElementById("canvas-input");
const sessionSelect = document.getElementById("session-select");
const requestCount = document.getElementById("request-count");
const previewButton = document.getElementById("preview-button");
const previewMessage = document.getElementById("preview-message");
const outlineResults = document.getElementById("outline-results");
const notes = document.getElementById("notes");
const review = document.getElementById("review");
const reviewBody = document.getElementById("review-body");
const saveButton = document.getElementById("save-button");
const saveMessage = document.getElementById("save-message");

// The file endings Groot reads, like ".pdf" and ".docx". The server puts them in the
// file picker's accept list. It still checks what each file really is from its contents.
const ENDINGS = outlineInput.accept.split(",");

let outlines = [];  // the outline files chosen so far
let tableRows = [];  // one entry for each row of the review table, made by makeRow

// ---------- 1. choosing files ----------

function addOutlines(files) {
  const problems = [];
  for (const file of files) {
    const name = file.name.toLowerCase();
    if (!ENDINGS.some((ending) => name.endsWith(ending))) {
      problems.push(`${file.name} is not a kind of file Groot can read. The kinds it reads are listed above.`);
    } else if (file.size > MAX_FILE_BYTES) {
      problems.push(`${file.name} is bigger than 10 MB.`);
    } else if (outlines.some((chosen) => chosen.name === file.name && chosen.size === file.size)) {
      problems.push(`${file.name} is already in the list.`);
    } else if (outlines.length === MAX_OUTLINES) {
      problems.push(`At most ${MAX_OUTLINES} outlines can be read at a time, so ${file.name} was left out.`);
    } else {
      outlines.push(file);
    }
  }
  show(fileMessage, {status: "error", message: problems.join(" ")});
  drawOutlineList();
}

function drawOutlineList() {
  outlineList.replaceChildren(...outlines.map((file, index) => {
    const remove = element("button", "Remove", "secondary");
    remove.type = "button";
    remove.setAttribute("aria-label", `Remove ${file.name}`);
    remove.addEventListener("click", () => {
      outlines.splice(index, 1);
      drawOutlineList();
    });
    const item = document.createElement("li");
    item.append(element("span", `${file.name} (${sizeText(file.size)})`), remove);
    return item;
  }));
  const count = outlines.length;
  requestCount.textContent = count === 0
    ? "Choose at least one outline to preview."
    : `Preview will use ${count} Gemini ${count === 1 ? "request" : "requests"}, one for each outline.`;
  previewButton.disabled = count === 0;
}

function sizeText(bytes) {
  return bytes < 1024 * 1024 ? `${Math.ceil(bytes / 1024)} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

// Dragging files. Stopping the browser's own handling everywhere means a file
// dropped next to the box is ignored, instead of opening in the browser.
window.addEventListener("dragover", (event) => {
  event.preventDefault();
  const overTheBox = dropZone.contains(event.target);
  event.dataTransfer.dropEffect = overTheBox ? "copy" : "none";
  dropZone.classList.toggle("dragging", overTheBox);
});
window.addEventListener("drop", (event) => {
  event.preventDefault();
  dropZone.classList.remove("dragging");
  if (dropZone.contains(event.target)) {
    addOutlines(event.dataTransfer.files);
  }
});

outlineInput.addEventListener("change", () => {
  addOutlines(outlineInput.files);
  outlineInput.value = "";  // so choosing the same file again still counts
});

document.getElementById("timetable-clear").addEventListener("click", () => {
  timetableInput.value = "";
});

// ---------- 2. preview ----------

previewButton.addEventListener("click", async () => {
  const form = new FormData();
  for (const file of outlines) {
    form.append("outlines", file);
  }
  if (timetableInput.files.length > 0) {
    form.append("timetable", timetableInput.files[0]);
  }
  const link = canvasInput.value.trim();
  if (link) {
    form.append("canvas_url", link);
  }
  form.append("session", sessionSelect.value);

  previewButton.disabled = true;
  review.hidden = true;
  outlineResults.replaceChildren();
  notes.replaceChildren();
  const which = outlines.length === 1 ? "your outline" : `your ${outlines.length} outlines`;
  show(previewMessage, {
    status: "working",
    message: `Reading ${which} with Gemini. This can take about half a minute for each outline.`,
  });
  try {
    // The browser sets the form's content type, with its boundary, by itself
    const result = await answer(await fetch("/groot/api/preview", {method: "POST", body: form}));
    show(previewMessage, result);
    if (result.status === "success") {
      drawPreview(result);
    }
  } catch {
    showOffline(previewMessage);
  } finally {
    previewButton.disabled = outlines.length === 0;
  }
});

function drawPreview(result) {
  outlineResults.replaceChildren(...result.outlines.map(
    (outline) => element("li", `${outline.file}: ${outline.message}`, outline.status),
  ));
  notes.replaceChildren(...result.notes.map((note) => element("li", note)));
  tableRows = result.rows.map(makeRow);
  reviewBody.replaceChildren(...tableRows.map((entry) => entry.tr));
  show(saveMessage, {status: "", message: ""});
  review.hidden = tableRows.length === 0;
}

// One row of the review table. Returns the row's data together with the
// parts of the table row that Save reads or changes later.
function makeRow(row) {
  const include = document.createElement("input");
  include.type = "checkbox";
  include.checked = row.include;
  // Only a date that is still to come can be saved
  include.disabled = row.status !== "exact" && row.status !== "assumed";
  include.setAttribute("aria-label", `Save ${row.title}`);
  const saveCell = document.createElement("td");
  saveCell.append(include);

  const deadline = document.createElement("td");
  deadline.append(element("span", row.title, "title"), element("span", row.subject, "subject"));
  if (row.weight_percent !== null) {
    deadline.append(element("span", `Worth ${row.weight_percent}% of the mark`, "weight"));
  }

  const due = document.createElement("td");
  let dateInput = null;
  if (row.status === "needs_input") {
    dateInput = document.createElement("input");
    dateInput.type = "text";
    dateInput.autocomplete = "off";
    dateInput.placeholder = "like 25 aug 9am";
    dateInput.setAttribute("aria-label", `Due date for ${row.title}`);
    // Typing a date makes the row saveable and ticks it. Clearing it unticks it again.
    dateInput.addEventListener("input", () => {
      const typed = dateInput.value.trim() !== "";
      include.disabled = !typed;
      include.checked = typed;
    });
    due.append(dateInput);
  } else {
    due.textContent = row.due_text || "No date yet";
  }

  const status = document.createElement("td");
  status.append(
    element("span", STATUS_TEXT[row.status], `badge ${row.status}`),
    element("span", SOURCE_TEXT[row.source], "source"),
  );

  const result = element("p", "", "row-result");  // filled in after Save
  const note = document.createElement("td");
  note.append(element("span", row.note), result);

  const tr = document.createElement("tr");
  tr.className = `row-${row.status}`;
  tr.append(saveCell, deadline, due, status, note);
  return {row, tr, include, dateInput, result};
}

// ---------- 3. save ----------

saveButton.addEventListener("click", async () => {
  const chosen = tableRows.filter((entry) => entry.include.checked);
  const rows = chosen.map((entry) => ({
    title: entry.row.title,
    // A typed date is sent as typed, and add_deadline works out words like "25 aug 9am"
    due_date: entry.dateInput ? entry.dateInput.value.trim() : entry.row.due_date,
    subject: entry.row.subject,
    weight_percent: entry.row.weight_percent,  // saved for the grade calculator
  }));
  saveButton.disabled = true;
  try {
    const result = await answer(await post("/groot/api/save", {rows}));
    show(saveMessage, result);
    if (result.status === "success") {
      result.results.forEach((saved, index) => showRowResult(chosen[index], saved));
    }
  } catch {
    showOffline(saveMessage);
  } finally {
    saveButton.disabled = false;
  }
});

// Show what happened to one row. A row that was saved cannot be saved twice.
function showRowResult(entry, saved) {
  entry.result.textContent = saved.status === "success" ? saved.message : `Not saved: ${saved.message}`;
  entry.result.className = `row-result ${saved.status}`;
  if (saved.status === "success") {
    entry.include.checked = false;
    entry.include.disabled = true;
    if (entry.dateInput) {
      entry.dateInput.disabled = true;
    }
    entry.tr.classList.add("saved");
  }
}
