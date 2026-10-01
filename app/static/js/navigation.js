"use strict";

(() => {
  const trigger = document.querySelector(".mobile-menu-toggle");
  const navigation = document.getElementById("site-navigation");
  if (!trigger || !navigation) return;
  const mobile = window.matchMedia("(max-width: 959px)");
  const icon = trigger.querySelector(".mobile-menu-icon");

  function setOpen(open) {
    trigger.setAttribute("aria-expanded", String(open));
    navigation.classList.toggle("is-open", open);
    icon.textContent = open ? "\u00d7" : "\u2630";
  }

  trigger.addEventListener("click", () => {
    setOpen(trigger.getAttribute("aria-expanded") !== "true");
  });
  navigation.addEventListener("click", (event) => {
    if (event.target.closest("a, button")) setOpen(false);
  });
  document.addEventListener("click", (event) => {
    if (!navigation.contains(event.target) && !trigger.contains(event.target)) setOpen(false);
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && trigger.getAttribute("aria-expanded") === "true") {
      setOpen(false);
      trigger.focus();
    }
  });
  mobile.addEventListener("change", () => setOpen(false));
})();
