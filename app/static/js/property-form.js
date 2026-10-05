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
const count = document.getElementById("photo-total-count");
const previews = document.getElementById("selected-photo-previews");
const existingCount = Number(count?.dataset.currentCount || 0);
const maxPhotos = Number(count?.dataset.maxPhotos || 20);
const uploadButton = document.querySelector('.photo-upload-button');
let previewUrls = [];
function updateSelectedPhotos() {
  previewUrls.forEach(url => URL.revokeObjectURL(url));
  previewUrls = [];
  previews.replaceChildren();
  const selected = Array.from(photos.files);
  count.textContent = String(existingCount + selected.length);
  const exceeded = existingCount + selected.length > maxPhotos;
  countError.hidden = !exceeded;
  photos.setCustomValidity(exceeded ? countError.textContent.trim() : "");
  selected.forEach((file, index) => {
    const item = document.createElement("li");
    const image = document.createElement("img");
    const url = URL.createObjectURL(file);
    previewUrls.push(url);
    image.src = url;
    image.alt = file.name;
    const actions = document.createElement("div");
    actions.className = "photo-thumb-actions";
    const remove = document.createElement("button");
    remove.type = "button";
    remove.textContent = previews.dataset.removeLabel;
    remove.setAttribute("aria-label", `${previews.dataset.removeLabel}: ${file.name}`);
    remove.addEventListener("click", () => {
      const remaining = new DataTransfer();
      selected.forEach((candidate, position) => {
        if (position !== index) remaining.items.add(candidate);
      });
      photos.files = remaining.files;
      updateSelectedPhotos();
    });
    actions.append(remove);
    item.append(image, actions);
    previews.append(item);
  });
  previews.hidden = selected.length === 0;
  if (uploadButton) uploadButton.hidden = selected.length === 0;
}
photos?.addEventListener("change", updateSelectedPhotos);
if (uploadButton) uploadButton.hidden = !photos?.files.length;
