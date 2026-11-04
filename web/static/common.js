// Small helpers shared by Groot's two pages.

// Send JSON to one of Groot's API routes. The browser adds the Origin header
// that the server checks, so only Groot's own pages can change anything.
export function post(path, data) {
  return fetch(path, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(data),
  });
}

// Every API answer is JSON with "status" and "message". If the server
// crashed it sends plain text instead, so that becomes a message too.
export async function answer(response) {
  const type = response.headers.get("Content-Type") || "";
  if (type.startsWith("application/json")) {
    return response.json();
  }
  return {
    status: "error",
    message: "Something went wrong inside Groot. The details are in the window where Groot is running.",
  };
}

// Show a message, coloured by its status: "success", "error" or "working".
// textContent shows the text exactly as it is, so it can never turn into HTML.
export function show(where, result) {
  where.textContent = result.message;
  where.className = `message ${result.status}`;
}

// The request never reached Groot, usually because it has stopped running.
export function showOffline(where) {
  show(where, {status: "error", message: "Groot did not answer. Check it is still running, then try again."});
}

// A new element holding plain text.
export function element(tag, text, className = "") {
  const node = document.createElement(tag);
  node.textContent = text;
  if (className) {
    node.className = className;
  }
  return node;
}
