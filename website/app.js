// Groot's website. It runs Groot's own Python code in this browser with Pyodide,
// so the deadlines, the dates and the page are exactly the laptop version's.
// Nothing is sent anywhere: the deadlines are kept in this browser's storage.
//
// home.js (the laptop version's script) asks a server for everything. Here,
// fetch() is swapped for a version that hands those requests to web/browser.py
// instead, then copies the deadlines file into this browser's storage.
import {loadPyodide} from "https://cdn.jsdelivr.net/pyodide/v314.0.7/full/pyodide.mjs";
import {show} from "./static/common.js";

const CODE = "/home/pyodide/groot-code";  // Groot's Python files, inside Pyodide's memory
const DATA = "/home/pyodide/groot-data";  // the deadlines file and the chosen session
const FILES = {deadlines: `${DATA}/deadlines.json`, settings: `${DATA}/groot_settings.json`};
// Where each file is kept in this browser's storage
const KEYS = {deadlines: "groot-deadlines", settings: "groot-settings"};
const LAST_BACKUP = "groot-last-backup";
const INSTALL_SEEN = "groot-install-tip-seen";
const FLASH = "groot-flash";  // a message to show after the page reloads
// The parts of the page drawn again after a change. The same list as refreshLists in home.js.
export const REDRAWN = ["heads-up", "due-soon-list", "deadline-table", "grades", "week-line", "uts-tip"];
// The requests that change something, so they are saved straight after
const CHANGES = new Set(["add", "done", "delete", "edit", "mark", "session", "restore", "examples"]);
const NOT_KEPT =
  "This browser is blocking Groot's storage (for example in a private window), " +
  "so your deadlines will be gone when you close this page.";

// localStorage or sessionStorage, or null when the browser blocks it
function storage(kind) {
  try {
    const store = window[kind];
    store.getItem("groot-test");
    return store;
  } catch {
    return null;
  }
}
const local = storage("localStorage");
const session = storage("sessionStorage");

let pyodide;
let browser;  // web/browser.py
let askedToKeep = false;

// Singapore time in Singapore, and Sydney time everywhere else, as on the laptop version
function country() {
  const zone = Intl.DateTimeFormat().resolvedOptions().timeZone || "";
  return zone === "Asia/Singapore" || zone === "Singapore" ? "SG" : "AU";
}

async function start() {
  pyodide = await loadPyodide();
  await pyodide.loadPackage("tzdata");  // the world's time zones, for Sydney and Singapore time
  const files = await (await fetch("py-files.json")).json();
  for (const path of files) {
    const response = await fetch(`py/${path}`);
    if (!response.ok) {
      throw new Error(`could not load ${path}`);
    }
    const full = `${CODE}/${path}`;
    pyodide.FS.mkdirTree(full.slice(0, full.lastIndexOf("/")));
    pyodide.FS.writeFile(full, await response.text());
  }
  // Groot reads the laptop's .env file with python-dotenv. The website has no .env file, so this stands in for it.
  pyodide.FS.writeFile(`${CODE}/dotenv.py`, "def dotenv_values(*args, **kwargs):\n    return {}\n");
  pyodide.FS.mkdirTree(DATA);
  for (const [name, path] of Object.entries(FILES)) {
    const saved = local && local.getItem(KEYS[name]);
    if (saved) {
      pyodide.FS.writeFile(path, saved);
    }
  }
  pyodide.runPython(`
import os, sys
sys.path.insert(0, ${JSON.stringify(CODE)})
os.environ["DEADLINES_FILE"] = ${JSON.stringify(FILES.deadlines)}
os.environ["DEADLINES_ICS_FILE"] = ${JSON.stringify(`${DATA}/deadlines.ics`)}
os.environ["GROOT_COUNTRY"] = ${JSON.stringify(country())}
`);
  browser = pyodide.pyimport("web.browser");
}

// Copy the deadlines file and the chosen session into this browser's storage. False if it is blocked.
function save() {
  if (!local) {
    return false;
  }
  try {
    for (const [name, path] of Object.entries(FILES)) {
      if (pyodide.FS.analyzePath(path).exists) {
        local.setItem(KEYS[name], pyodide.FS.readFile(path, {encoding: "utf8"}));
      }
    }
  } catch {
    return false;
  }
  if (!askedToKeep && navigator.storage && navigator.storage.persist) {
    // Ask the browser to keep Groot's data even when the device runs low on space. Some browsers always say no.
    askedToKeep = true;
    navigator.storage.persist().catch(() => {});
  }
  return true;
}

// Run one request in web/browser.py, the way app.py answers it on the laptop
function run(action, body = "{}") {
  let result;
  try {
    result = JSON.parse(browser.handle_json(action, body));
  } catch (error) {
    console.error(error);
    return {status: "error", message: "Something went wrong inside Groot. Reload the page and try again."};
  }
  if (CHANGES.has(action) && result.status === "success" && !save()) {
    result.message += ` But ${NOT_KEPT.charAt(0).toLowerCase()}${NOT_KEPT.slice(1)}`;
  }
  return result;
}

const json = (result) => new Response(JSON.stringify(result), {headers: {"Content-Type": "application/json"}});

// Answer home.js's requests here, instead of over the internet
const realFetch = window.fetch.bind(window);
window.fetch = async (input, init = {}) => {
  const url = typeof input === "string" ? input : input.url;
  if (url === "/groot") {
    const page = `<!doctype html><html><body>${browser.home_html()}</body></html>`;
    return new Response(page, {headers: {"Content-Type": "text/html; charset=utf-8"}});
  }
  const match = /^\/groot\/api\/([a-z]+)$/.exec(url);
  if (!match) {
    return realFetch(input, init);
  }
  const result = run(match[1], typeof init.body === "string" ? init.body : "{}");
  if (match[1] === "export" && result.calendar) {
    return new Response(result.calendar, {headers: {"Content-Type": "text/calendar; charset=utf-8"}});
  }
  return json(result);
};

// Draw the lists again from the deadlines, like refreshLists in home.js
async function redraw() {
  const fresh = new DOMParser().parseFromString(await (await fetch("/groot")).text(), "text/html");
  for (const id of REDRAWN) {
    document.getElementById(id).replaceWith(fresh.getElementById(id));
  }
}

// Hand a file to the browser to save, the same as clicking a download link
function download(blob, name) {
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = name;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(link.href), 10000);
}

function daysSince(time) {
  return Math.floor((Date.now() - Number(time)) / 86400000);
}

// The buttons in "Your data in this browser"
function setUpWebsiteButtons() {
  const message = document.getElementById("browser-message");
  if (!local) {
    show(message, {status: "error", message: NOT_KEPT});
  }

  document.getElementById("backup-button").addEventListener("click", () => {
    const result = run("backup");
    if (result.status !== "success") {
      show(message, result);
      return;
    }
    const today = new Date().toLocaleDateString("en-CA");  // like 2026-11-24, in the student's own time
    download(new Blob([result.backup], {type: "application/json"}), `groot-backup-${today}.json`);
    try {
      local.setItem(LAST_BACKUP, String(Date.now()));
    } catch {}
    show(message, {status: "success", message: `${result.message} Keep the file somewhere safe, like your cloud drive.`});
  });

  document.getElementById("restore-input").addEventListener("change", async (event) => {
    const file = event.target.files[0];
    event.target.value = "";  // so choosing the same file again still works
    if (!file) {
      return;
    }
    if (file.size > 2_000_000) {
      show(message, {status: "error", message: "That file is too big to be a Groot backup, so nothing was changed."});
      return;
    }
    if (!confirm("Replace the deadlines in this browser with the ones in this backup?")) {
      return;
    }
    const result = run("restore", JSON.stringify({backup: await file.text()}));
    if (result.status === "success") {
      // Start again, so every part of the page (including the session picker) shows the restored data
      try {
        session.setItem(FLASH, result.message);
      } catch {}
      location.reload();
    } else {
      show(message, result);
    }
  });

  document.getElementById("examples-button").addEventListener("click", async () => {
    const result = run("examples");
    show(message, result);
    if (result.status === "success") {
      await redraw();
    }
  });
}

// On an iPhone or iPad, suggest adding Groot to the Home Screen, where Safari does not erase its data.
// iPads say they are Macs, so a Mac with a touch screen counts as an iPad.
function suggestHomeScreen() {
  const apple = /iPhone|iPad|iPod/.test(navigator.userAgent) || (/Macintosh/.test(navigator.userAgent) && navigator.maxTouchPoints > 1);
  const installed = navigator.standalone === true || matchMedia("(display-mode: standalone)").matches;
  let seen = null;
  try {
    seen = local.getItem(INSTALL_SEEN);
  } catch {}
  const tip = document.getElementById("install-tip");
  tip.hidden = !apple || installed || seen === "yes";
  document.getElementById("install-ok").addEventListener("click", () => {
    tip.hidden = true;
    try {
      local.setItem(INSTALL_SEEN, "yes");
    } catch {}
  });
}

// A gentle reminder to download a backup, once there is something worth keeping
function remindAboutBackups() {
  const top = document.getElementById("top-message");
  let flash = null;
  let count = 0;
  let last = null;
  try {
    flash = session.getItem(FLASH);
    session.removeItem(FLASH);
  } catch {}
  if (flash) {
    show(top, {status: "success", message: flash});
    return;
  }
  try {
    count = JSON.parse(local.getItem(KEYS.deadlines) || "[]").length;
    last = local.getItem(LAST_BACKUP);
  } catch {}
  if (count === 0) {
    return;
  }
  if (!last) {
    show(top, {status: "working", message: 'Tip: use "Download backup" at the bottom of this page now and then, in case this browser\'s data is cleared.'});
  } else if (daysSince(last) >= 7) {
    show(top, {status: "working", message: `Your last backup was ${daysSince(last)} days ago. "Download backup" is at the bottom of this page.`});
  }
}

try {
  await start();
  document.getElementById("groot").innerHTML = browser.home_html();
  document.getElementById("loading").remove();
  await import("./static/home.js");  // the laptop version's own script, which now talks to browser.py
  setUpWebsiteButtons();
  suggestHomeScreen();
  remindAboutBackups();
} catch (error) {
  console.error(error);
  const loading = document.getElementById("loading");
  loading.replaceChildren();
  const note = document.createElement("p");
  note.textContent =
    "Groot could not start. Check your internet connection, then reload the page. " +
    "Any deadlines you saved are still in this browser.";
  note.className = "message error";
  loading.append(note);
}
