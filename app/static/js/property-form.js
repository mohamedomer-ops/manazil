"use strict";
// Pure flow helpers consume server metadata; there is no client property matrix.
const ManazilPropertyWizard = {
  applicability(metadata, type, transaction) {
    return metadata.types[type]?.transactions[transaction] || {};
  },
  flow(metadata, type, transaction) {
    const rules = this.applicability(metadata, type, transaction);
    return ["purpose", "property", ...(rules.property_occupancy && rules.property_occupancy !== "inapplicable" ? ["occupancy"] : []),
      "location", "details", "transaction", "description", "photos", "contact", "review"];
  },
  required(metadata, field, type, transaction) {
    const same = metadata.original?.property_type === type && metadata.original?.transaction_type === transaction;
    return this.applicability(metadata, type, transaction)[field] === "required" && !(same && (metadata.legacy_missing || []).includes(field));
  },
  reviewFields(metadata, type, transaction, entries) {
    const rules = this.applicability(metadata, type, transaction);
    return entries.filter(entry => rules[entry.name] !== "inapplicable" && entry.value != null && String(entry.value).trim() !== "");
  }
};
if (typeof module !== "undefined") module.exports = ManazilPropertyWizard;
if (typeof document !== "undefined") {
const form = document.getElementById("property-form");
if (form) {
const metadata = JSON.parse(document.getElementById("property-wizard-rules").textContent);
const sections = [...form.querySelectorAll("[data-wizard-step]")];
const progress = document.getElementById("wizard-progress");
const navigation = document.getElementById("wizard-navigation");
const back = document.getElementById("wizard-back");
const next = document.getElementById("wizard-next");
const state = document.getElementById("wizard-section");
const review = document.getElementById("wizard-review");
const completed = new Set();
const value = name => {
  const controls = [...form.querySelectorAll(`[name="${name}"]`)];
  if (controls[0]?.type === "radio") return controls.find(control => control.checked)?.value || "";
  return controls[0]?.value || "";
};
const choices = () => [value("property_type"), value("transaction_type")];
const flow = () => ManazilPropertyWizard.flow(metadata, ...choices());
let current = flow().includes(form.dataset.initialSection) ? form.dataset.initialSection : "purpose";
function updateApplicability() {
  const [type, transaction] = choices();
  const rules = ManazilPropertyWizard.applicability(metadata, type, transaction);
  form.querySelectorAll("[data-field]").forEach(group => {
    const name = group.dataset.field;
    const applicable = !(name in metadata.labels) || (rules[name] && rules[name] !== "inapplicable");
    group.hidden = !applicable;
    group.querySelectorAll("input, select, textarea").forEach(control => {
      control.disabled = !applicable;
      if (name in metadata.labels) control.required = applicable && ManazilPropertyWizard.required(metadata, name, type, transaction);
    });
  });
  document.getElementById("rent-period-field").hidden = rules.rent_period === "inapplicable" || !rules.rent_period;
  form.querySelector("[data-rental-hint]").hidden = rules.available_from_date === "inapplicable" || !rules.available_from_date;
  const priceLabel = form.querySelector('[data-field="price"] label');
  priceLabel.textContent = transaction === "sale" ? review.dataset.salePrice : review.dataset.rentPrice;
  form.querySelector('[data-field="price"]').dataset.label = priceLabel.textContent;
}
function validate(section) {
  const controls = [...section.querySelectorAll("input, select, textarea")].filter(control => !control.disabled && control.type !== "hidden");
  let first = null;
  controls.forEach(control => {
    const invalid = !control.checkValidity();
    control.setAttribute("aria-invalid", String(invalid));
    let message = section.querySelector(`[data-client-error="${control.name}"]`);
    if (invalid && !message) {
      message = document.createElement("p");
      message.className = "field-error";
      message.dataset.clientError = control.name;
      message.id = `wizard-error-${control.name}`;
      control.closest("[data-field]")?.append(message);
    }
    if (message) {
      message.hidden = !invalid;
      message.textContent = control.validity.valueMissing ? form.dataset.requiredMessage : form.dataset.invalidMessage;
      if (invalid) control.setAttribute("aria-describedby", [...new Set([...(control.getAttribute("aria-describedby") || "").split(" "), message.id])].filter(Boolean).join(" "));
    }
    if (invalid && !first) first = control;
  });
  document.getElementById("wizard-validation-message").hidden = !first;
  if (first) first.focus();
  return !first;
}
function renderReview() {
  review.replaceChildren();
  sections.filter(section => section.dataset.wizardStep !== "review" && flow().includes(section.dataset.wizardStep)).forEach(section => {
    const block = document.createElement("section");
    const heading = document.createElement("h3");
    heading.textContent = section.dataset.stepLabel;
    const edit = document.createElement("button");
    edit.type = "button"; edit.className = "wizard-review-edit";
    edit.textContent = review.dataset.edit;
    edit.setAttribute("aria-label", `${review.dataset.edit}: ${section.dataset.stepLabel}`);
    edit.addEventListener("click", () => show(section.dataset.wizardStep));
    block.append(heading, edit);
    const list = document.createElement("dl");
    const entries = [...section.querySelectorAll("[data-field]")].filter(group => !group.hidden).map(group => {
      const control = group.querySelector("input, select, textarea");
      let display = value(control?.name);
      if (control?.type === "radio") display = group.querySelector("input:checked")?.dataset.choiceLabel || "";
      else if (control?.type === "checkbox") display = control.checked ? review.dataset.yes : review.dataset.no;
      else if (control?.tagName === "SELECT") display = control.selectedOptions[0]?.textContent.trim() || "";
      return {name: control?.name, label: group.dataset.label || group.querySelector("label")?.textContent, value: value(control?.name) ? display : control?.type === "checkbox" ? display : ""};
    });
    ManazilPropertyWizard.reviewFields(metadata, ...choices(), entries).forEach(entry => {
      const row = document.createElement("div"), label = document.createElement("dt"), text = document.createElement("dd");
      label.textContent = entry.label; text.textContent = entry.value;
      row.append(label, text); list.append(row);
    });
    if (section.dataset.wizardStep === "photos") {
      const text = document.createElement("p"); text.textContent = `${review.dataset.photos}: ${document.getElementById("photo-total-count").textContent}`;
      block.append(text);
      const primary = section.querySelector(".primary-photo-label")?.closest("li")?.querySelector("img") || section.querySelector(".photo-thumbnails img");
      if (primary) { const image = primary.cloneNode(); image.className = "wizard-review-photo"; block.append(image); }
    }
    block.append(list); review.append(block);
  });
}
function show(key, focus = true) {
  updateApplicability();
  const path = flow();
  current = path.includes(key) ? key : "property";
  state.value = current;
  sections.forEach(section => { section.hidden = section.dataset.wizardStep !== current; });
  progress.replaceChildren();
  path.forEach((key, index) => {
    const section = sections.find(section => section.dataset.wizardStep === key);
    const button = document.createElement("button"); button.type = "button";
    const progressState = key === current ? "current" : completed.has(key) ? "completed" : "upcoming";
    button.dataset.progressState = progressState;
    const dot = document.createElement("span");
    dot.className = "wizard-progress-dot";
    dot.setAttribute("aria-hidden", "true");
    const label = document.createElement("span");
    label.textContent = section.dataset.stepLabel;
    button.append(dot, label);
    button.setAttribute("aria-label", `${section.dataset.stepLabel}: ${review.dataset[progressState]}`);
    button.disabled = index > path.indexOf(current) && !completed.has(key);
    if (key === current) button.setAttribute("aria-current", "step");
    button.addEventListener("click", () => show(key)); progress.append(button);
  });
  progress.querySelector('[aria-current="step"]')?.scrollIntoView({block: "nearest", inline: "nearest", behavior: "auto"});
  back.disabled = current === path[0]; next.hidden = current === "review";
  const active = sections.find(section => section.dataset.wizardStep === current);
  document.getElementById("wizard-status").textContent = active.dataset.stepLabel;
  if (current === "review") renderReview();
  if (focus) active.querySelector("h2").focus();
  document.dispatchEvent(new CustomEvent("property-wizard-section", {detail: current}));
}
function advance() {
  const active = sections.find(section => section.dataset.wizardStep === current);
  if (!validate(active)) return;
  completed.add(current);
  const path = flow(); show(path[path.indexOf(current) + 1] || "review");
}
back.addEventListener("click", () => { const path = flow(); show(path[Math.max(0, path.indexOf(current) - 1)]); });
next.addEventListener("click", advance);
["transaction_type", "property_type", "property_occupancy"].forEach(name => {
  form.querySelectorAll(`[name="${name}"]`).forEach(control => control.addEventListener("click", () => {
    const index = flow().indexOf(current);
    flow().slice(index).forEach(key => completed.delete(key));
    updateApplicability(); advance();
  }));
});
form.addEventListener("keydown", event => {
  if (event.key === "Enter" && event.target.matches("input:not([type=radio]):not([type=file]), select") && current !== "review") {
    event.preventDefault(); advance();
  }
});
form.addEventListener("submit", event => {
  if ((event.submitter?.value || "submit") !== "submit") return;
  updateApplicability();
  for (const key of flow().filter(key => key !== "review")) {
    const section = sections.find(section => section.dataset.wizardStep === key);
    // Reveal before validation so an invalid control can receive focus.
    const invalid = [...section.querySelectorAll("input,select,textarea")].some(control => !control.disabled && !control.checkValidity());
    if (invalid) { event.preventDefault(); show(key); validate(section); return; }
  }
  if (current !== "review") { event.preventDefault(); show("review"); }
});
form.classList.add("wizard-enhanced");
progress.hidden = false; navigation.hidden = false;
show(current, false);
metadata.errors.forEach(name => {
  const message = document.getElementById(`${name}-error`);
  form.querySelectorAll(`[name="${name}"]`).forEach(control => {
    control.setAttribute("aria-invalid", "true");
    if (message) control.setAttribute("aria-describedby", message.id);
  });
});
if (metadata.errors.length) {
  const first = form.querySelector(`[name="${metadata.errors[0]}"]:not(:disabled):not([type="hidden"])`);
  (first || sections.find(section => section.dataset.wizardStep === current).querySelector("h2")).focus();
}
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

}
}
