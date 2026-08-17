const tabLogin = document.getElementById("tabLogin");
const tabSignup = document.getElementById("tabSignup");
const loginForm = document.getElementById("loginForm");
const signupForm = document.getElementById("signupForm");

tabLogin.addEventListener("click", () => {
  tabLogin.classList.add("active"); tabSignup.classList.remove("active");
  loginForm.hidden = false; signupForm.hidden = true;
});
tabSignup.addEventListener("click", () => {
  tabSignup.classList.add("active"); tabLogin.classList.remove("active");
  signupForm.hidden = false; loginForm.hidden = true;
});

loginForm.addEventListener("submit", async e => {
  e.preventDefault();
  const errEl = document.getElementById("loginError");
  errEl.textContent = "";
  try {
    const res = await fetch("/api/login", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email: document.getElementById("loginEmail").value,
        password: document.getElementById("loginPassword").value,
      }),
    });
    const data = await res.json();
    if (!res.ok) { errEl.textContent = data.error || "Sign in failed."; return; }
    window.location.href = "/";
  } catch (err) { errEl.textContent = "Something went wrong. Try again."; }
});

signupForm.addEventListener("submit", async e => {
  e.preventDefault();
  const errEl = document.getElementById("signupError");
  errEl.textContent = "";
  try {
    const res = await fetch("/api/signup", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: document.getElementById("signupName").value,
        email: document.getElementById("signupEmail").value,
        password: document.getElementById("signupPassword").value,
      }),
    });
    const data = await res.json();
    if (!res.ok) { errEl.textContent = data.error || "Sign up failed."; return; }
    window.location.href = "/";
  } catch (err) { errEl.textContent = "Something went wrong. Try again."; }
});

// ---------------- forgot password ----------------

const forgotLink = document.getElementById("forgotLink");
const backToLogin = document.getElementById("backToLogin");
const forgotForm = document.getElementById("forgotForm");

if (forgotLink && forgotForm) {
  forgotLink.addEventListener("click", e => {
    e.preventDefault();
    loginForm.hidden = true;
    forgotForm.hidden = false;
  });
  backToLogin.addEventListener("click", e => {
    e.preventDefault();
    forgotForm.hidden = true;
    loginForm.hidden = false;
  });

  forgotForm.addEventListener("submit", async e => {
    e.preventDefault();
    const errEl = document.getElementById("forgotError");
    const successEl = document.getElementById("forgotSuccess");
    errEl.textContent = "";
    successEl.style.display = "none";
    try {
      const res = await fetch("/api/forgot-password", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: document.getElementById("forgotEmail").value }),
      });
      const data = await res.json();
      if (!res.ok) { errEl.textContent = data.error || "Something went wrong."; return; }
      successEl.style.display = "block";
    } catch (err) {
      errEl.textContent = "Something went wrong. Try again.";
    }
  });
}
