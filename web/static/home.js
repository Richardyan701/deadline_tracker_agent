// Agent Groot's home page: mark done, edit, delete, add a deadline, enter marks and export to a calendar.
// Each button calls Groot's JSON API, which runs the same tools as the chat.
// Then the server draws the lists again, so they always match the deadlines file.
import {answer, post, show, showOffline} from "./common.js";

const topMessage = document.getElementById("top-message");
const tableMessage = document.getElementById("table-message");
const addForm = document.getElementById("add-form");
const addMessage = document.getElementById("add-message");
const exportButton = document.getElementById("export-button");
const markMessage = document.getElementById("mark-message");

// Ask the server for this page again and swap in its fresh lists.
async function refreshLists() {
  const response = await fetch("/groot");
  if (!response.ok) {
    throw new Error(`the home page answered ${response.status}`);  // shown as "Groot did not answer"
  }
  const fresh = new DOMParser().parseFromString(await response.text(), "text/html");
  for (const id of ["heads-up", "due-soon-list", "deadline-table", "grades"]) {
    document.getElementById(id).replaceWith(fresh.getElementById(id));
  }
}

// The Mark done and Delete buttons. One listener for the whole page also
// works for the buttons in lists that are drawn again later.
document.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button) {
    return;
  }
  const title = button.dataset.title;
  const action = button.dataset.action;  // "done" or "delete"
  if (action === "delete" && !confirm(`Are you sure you want to delete "${title}"? This cannot be undone.`)) {
    return;
  }
  button.disabled = true;
  try {
    show(tableMessage, await answer(await post(`/groot/api/${action}`, {title})));
    await refreshLists();
    tableMessage.focus();  // the button is gone now, so keyboard users continue from the message
  } catch {
    showOffline(tableMessage);
    button.disabled = false;
  }
});

// The Edit box. An Edit button opens it filled in with that deadline.
const editDialog = document.getElementById("edit-dialog");
const editForm = document.getElementById("edit-form");
const editMessage = document.getElementById("edit-message");
let editing = null;  // the deadline being edited: its title, due date and subject as saved

document.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-edit]");
  if (!button) {
    return;
  }
  editing = {title: button.dataset.title, due: button.dataset.due, subject: button.dataset.subject};
  editForm.elements.new_title.value = editing.title;
  editForm.elements.due_date.value = editing.due;
  editForm.elements.subject.value = editing.subject;
  show(editMessage, {status: "", message: ""});
  editDialog.showModal();
});

document.getElementById("edit-cancel").addEventListener("click", () => editDialog.close());

editForm.addEventListener("submit", async (event) => {
  event.preventDefault();  // keep the box open until Groot says it worked
  const fields = new FormData(editForm);
  const button = editForm.querySelector("button[type=submit]");
  button.disabled = true;
  try {
    // A date left as it was is sent empty, which means "keep it". So a deadline
    // that is already overdue can still be renamed without its old date being refused.
    const due = fields.get("due_date").trim();
    const result = await answer(await post("/groot/api/edit", {
      title: editing.title,
      new_title: fields.get("new_title"),
      due_date: due === editing.due ? "" : due,
      subject: fields.get("subject"),
    }));
    if (result.status === "success") {
      editDialog.close();
      show(tableMessage, result);
      await refreshLists();
      tableMessage.focus();
    } else {
      show(editMessage, result);  // edit_deadline's own message, for example an unclear date
    }
  } catch {
    showOffline(editMessage);
  } finally {
    button.disabled = false;
  }
});

addForm.addEventListener("submit", async (event) => {
  event.preventDefault();  // stay on this page instead of sending the form the old way
  const fields = new FormData(addForm);
  const button = addForm.querySelector("button");
  button.disabled = true;
  try {
    const result = await answer(await post("/groot/api/add", {
      title: fields.get("title"),
      due_date: fields.get("due_date"),
      subject: fields.get("subject"),
    }));
    show(addMessage, result);  // the add_deadline tool's own message, good or bad
    if (result.status === "success") {
      addForm.reset();
      await refreshLists();
    }
  } catch {
    showOffline(addMessage);
  } finally {
    button.disabled = false;
  }
});

// The Save mark form. It is drawn again after every change, so one listener
// on the whole page catches it, the same way as the Mark done buttons.
document.addEventListener("submit", async (event) => {
  if (event.target.id !== "mark-form") {
    return;
  }
  event.preventDefault();
  const form = event.target;
  const fields = new FormData(form);
  const button = form.querySelector("button");
  button.disabled = true;
  try {
    // Text is sent as typed. set_mark checks it is a number from 0 to 100 and explains any problem.
    const result = await answer(await post("/groot/api/mark", {
      title: fields.get("title"),
      mark_percent: fields.get("mark_percent"),
      weight_percent: fields.get("weight_percent"),
    }));
    show(markMessage, result);
    if (result.status === "success") {
      await refreshLists();  // a fresh form and fresh summaries
    }
  } catch {
    showOffline(markMessage);
  } finally {
    button.disabled = false;
  }
});

exportButton.addEventListener("click", async () => {
  exportButton.disabled = true;
  try {
    const response = await post("/groot/api/export", {});
    if ((response.headers.get("Content-Type") || "").startsWith("text/calendar")) {
      download(await response.blob(), "deadlines.ics");
      show(topMessage, {
        status: "success",
        message: "Downloaded deadlines.ics. Open it to add your unfinished deadlines to Google Calendar, Outlook or your phone.",
      });
    } else {
      show(topMessage, await answer(response));  // for example, nothing to export yet
    }
  } catch {
    showOffline(topMessage);
  } finally {
    exportButton.disabled = false;
  }
});

// Hand a file to the browser to save, the same as clicking a download link.
function download(blob, name) {
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = name;
  document.body.append(link);
  link.click();
  link.remove();
  // Free the file's memory once the browser has had time to start saving it
  setTimeout(() => URL.revokeObjectURL(link.href), 10000);
}
