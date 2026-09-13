async function checkAuth() {
  const res = await fetch("/api/auth/status");
  const data = await res.json();
  if (data.authenticated) {
    window.location.href = "/index.html";
  }
}

checkAuth();

document.getElementById("login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const password = document.getElementById("password").value;
  const errorEl = document.getElementById("login-error");

  errorEl.hidden = true;

  const res = await fetch("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password }),
  });

  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    errorEl.textContent = data.error || "Login failed";
    errorEl.hidden = false;
    return;
  }

  window.location.href = "/index.html";
});
