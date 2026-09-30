"use strict";
const category = document.querySelectorAll('input[name="transaction_type"]');
const rentPeriod = document.getElementById("rent-period-field");
const periodChoices = document.querySelectorAll('input[name="rent_period"]');
function updatePeriod() {
  const sale = document.querySelector('input[name="transaction_type"]:checked')?.value === "sale";
  rentPeriod.hidden = sale;
  periodChoices.forEach(input => {
    input.disabled = sale;
    input.required = !sale;
  });
}
category.forEach(input => input.addEventListener("change", updatePeriod));
updatePeriod();
const photos = document.getElementById("photos");
const countError = document.getElementById("photo-count-error");
const existingCount = document.querySelectorAll(".photo-thumbnails li").length;
photos?.addEventListener("change", () => {
  const exceeded = existingCount + photos.files.length > 20;
  countError.hidden = !exceeded;
  photos.setCustomValidity(exceeded ? "Maximum 20 photos" : "");
  if (exceeded) photos.value = "";
});
