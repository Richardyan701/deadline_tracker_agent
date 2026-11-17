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
const timetableField = document.getElementById("timetable-field");
const timetableInput = document.getElementById("timetable-input");
const canvasField = document.getElementById("canvas-field");
const canvasInput = document.getElementById("canvas-input");
const sessionSelect = document.getElementById("session-select");
const customField = document.getElementById("custom-field");
const customWeek1 = document.getElementById("custom-week1");
const customWeeks = document.getElementById("custom-weeks");
const customBreakAfter = document.getElementById("custom-break-after");
const customBreakWeeks = document.getElementById("custom-break-weeks");
const customMessage = document.getElementById("custom-message");
const requestCount = document.getElementById("request-count");
const previewButton = document.getElementById("preview-button");
const previewMessage = document.getElementById("preview-message");
const outlineResults = document.getElementById("outline-results");
const notes = document.getElementById("notes");
const review = document.getElementById("review");
const reviewBody = document.getElementById("review-body");
const saveButton = document.getElementById("save-button");
const saveMessage = document.getElementById("save-message");

// What each university can add to its outlines. Only UTS timetables can be
// read so far, and only UTS and USyd use Canvas (UNSW and Macquarie use Moodle).
const USES_TIMETABLE = ["uts"];
const USES_CANVAS = ["uts", "usyd"];
// Where the browser remembers the session picked last time, so it is only chosen once
const REMEMBERED_SESSION = "groot-session";
// The picker's value for "My university is not listed", and where its typed dates are remembered
const CUSTOM_CHOICE = "CUSTOM";
const REMEMBERED_CUSTOM = "groot-custom-session";

// The file endings Groot reads, like ".pdf" and ".docx". The server puts them in the
// file picker's accept list. It still checks what each file really is from its contents.
const ENDINGS = outlineInput.accept.split(",");

let outlines = [];  // the outline files chosen so far
let tableRows = [];  // one entry for each row of the review table, made by makeRow

// ---------- 1. choosing the university and files ----------

// The university of the session picked, like "uts", or "" while none is picked
function chosenUniversity() {
  const option = sessionSelect.selectedOptions[0];
  return option ? option.dataset.university || "" : "";
}

// What is wrong with the dates typed for "My university is not listed", or "" if they are fine.
// The server checks the same rules again (calendars.py).
function customProblem() {
  const weeks = Number(customWeeks.value);
  const after = Number(customBreakAfter.value);
  const length = Number(customBreakWeeks.value);
  if (!customWeek1.value) {
    return "Choose a day in week 1.";
  }
  if (!Number.isInteger(weeks) || weeks < 1 || weeks > Number(customWeeks.max)) {
    return `The number of teaching weeks must be from 1 to ${customWeeks.max}.`;
  }
  if (!Number.isInteger(after) || !Number.isInteger(length) || after < 0 || length < 0) {
    return "The break must be given in whole weeks.";
  }
  if ((after === 0) !== (length === 0)) {
    return "Fill in both break boxes, or leave both at 0 for no break.";
  }
  if (after >= weeks) {
    return "The break must come before the last teaching week.";
  }
  if (length > Number(customBreakWeeks.max)) {
    return `The break can be at most ${customBreakWeeks.max} weeks long.`;
  }
  return "";
}

// The session code to send: the picker's value, or for "My university is not listed" the code
// built from the typed dates, like "CUSTOM:2027-03-01:12:6:1". "" means nothing usable is chosen yet.
function sessionCode() {
  if (sessionSelect.value !== CUSTOM_CHOICE) {
    return sessionSelect.value;
  }
  if (customProblem()) {
    return "";
  }
  return `CUSTOM:${customWeek1.value}:${Number(customWeeks.value)}:${Number(customBreakAfter.value)}:${Number(customBreakWeeks.value)}`;
}

// Show only the extra fields the chosen university can use, and empty the ones
// that are hidden, so a file or link chosen for another university is never sent.
function showFieldsForUniversity() {
  const university = chosenUniversity();
  timetableField.hidden = !USES_TIMETABLE.includes(university);
  if (timetableField.hidden) {
    timetableInput.value = "";
  }
  canvasField.hidden = !USES_CANVAS.includes(university);
  if (canvasField.hidden) {
    canvasInput.value = "";
  }
  customField.hidden = sessionSelect.value !== CUSTOM_CHOICE;
}

// Preview needs a session and at least one outline. Say which one is missing.
function updatePreviewButton() {
  const count = outlines.length;
  const typing = sessionSelect.value === CUSTOM_CHOICE;
  show(customMessage, {status: "error", message: typing ? customProblem() : ""});
  if (sessionSelect.value === "") {
    requestCount.textContent = "Choose your university and session to preview.";
  } else if (sessionCode() === "") {
    requestCount.textContent = "Fill in your session's dates to preview.";
  } else if (count === 0) {
    requestCount.textContent = "Choose at least one outline to preview.";
  } else {
    requestCount.textContent = `Preview will use ${count} Gemini ${count === 1 ? "request" : "requests"}, one for each outline.`;
  }
  previewButton.disabled = count === 0 || sessionCode() === "";
}

// Typing a date for "My university is not listed" is remembered too, so it is only typed once
for (const input of [customWeek1, customWeeks, customBreakAfter, customBreakWeeks]) {
  input.addEventListener("input", () => {
    try {
      const typed = [customWeek1.value, customWeeks.value, customBreakAfter.value, customBreakWeeks.value];
      localStorage.setItem(REMEMBERED_CUSTOM, JSON.stringify(typed));
    } catch {}
    updatePreviewButton();
  });
}

sessionSelect.addEventListener("change", () => {
  // Remembering is only a convenience, so a browser that blocks storage is fine
  try {
    localStorage.setItem(REMEMBERED_SESSION, sessionSelect.value);
  } catch {}
  showFieldsForUniversity();
  updatePreviewButton();
});

// Start on the session picked last time, if the picker still offers it
try {
  const remembered = localStorage.getItem(REMEMBERED_SESSION);
  if (remembered && [...sessionSelect.options].some((option) => option.value === remembered)) {
    sessionSelect.value = remembered;
  }
} catch {}
try {
  const typed = JSON.parse(localStorage.getItem(REMEMBERED_CUSTOM) || "null");
  if (Array.isArray(typed) && typed.length === 4) {
    [customWeek1.value, customWeeks.value, customBreakAfter.value, customBreakWeeks.value] = typed;
  }
} catch {}
showFieldsForUniversity();
updatePreviewButton();

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
  updatePreviewButton();
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
  form.append("session", sessionCode());

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
    updatePreviewButton();
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
