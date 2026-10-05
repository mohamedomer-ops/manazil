"use strict";

document.querySelectorAll("[data-password-toggle]").forEach((toggle) => {
  const input = document.getElementById(toggle.getAttribute("aria-controls"));
  if (!input) return;

  toggle.addEventListener("click", () => {
    const showPassword = input.type === "password";
    input.type = showPassword ? "text" : "password";
    toggle.setAttribute("aria-label", showPassword ? toggle.dataset.hideLabel : toggle.dataset.showLabel);
    toggle.setAttribute("aria-pressed", String(showPassword));
  });
});
