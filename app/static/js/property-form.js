"use strict";
// Pure flow helpers consume server metadata; there is no client property matrix.
const ManazilPropertyWizard = {
  showContinue(section, current) { return section === current; },
  changedSinceAcceptance(approved, value) { return approved !== undefined && approved !== value; },
  shouldConfirmCancel({changed, choice, stagedCount, editing, entered}) {
    return Boolean(changed || choice || stagedCount > 0 || (!editing && entered));
  },
  progressive(path, completed, valid, through = null) {
    // A single contiguous prefix is visible; its final section is the frontier.
    const accepted = path.filter(key => completed.has(key) && valid[key]);
    let end = 0;
    while (end < path.length - 1 && accepted.includes(path[end])) end++;
    end = Math.max(end, path.indexOf(through));
    return {visible: path.slice(0, end + 1), current: path[end],
      accepted, completed: path.slice(0, end).filter(key => accepted.includes(key))};
  },
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
const state = document.getElementById("wizard-section");
const review = document.getElementById("wizard-review");
const cancel = document.getElementById("property-leave");
const cancelDialog = document.getElementById("property-leave-dialog");
// Compare controls without resetting the form or touching staged photo records.
const cancelSnapshot = () => JSON.stringify([...form.querySelectorAll("input,select,textarea")]
  .filter(control => control.name && !control.name.startsWith("_") && control.name !== "csrf_token")
  .map(control => [control.name, control.type === "file" ? [...control.files].map(file => [file.name, file.size, file.lastModified]) :
    control.type === "radio" || control.type === "checkbox" ? control.checked : control.value]));
let originalSnapshot = cancelSnapshot();
let meaningfulChoice = false;
form.querySelectorAll('.choice-button input').forEach(control => control.addEventListener('click', () => { meaningfulChoice = true; }));
function hasUnsavedPosting() {
  const entered = ['property_type', 'title_ar', 'description_ar', 'comment', 'size', 'neighborhood_ar', 'latitude']
    .some(name => [...form.querySelectorAll(`[name="${name}"]`)].some(control =>
      control.type === 'radio' ? control.checked : control.value.trim() !== ''));
  return ManazilPropertyWizard.shouldConfirmCancel({changed: cancelSnapshot() !== originalSnapshot,
    choice: meaningfulChoice || cancel.dataset.rerendered === 'true', stagedCount: Number(cancel.dataset.stagedCount), editing: cancel.dataset.editing === 'true', entered});
}
cancel.addEventListener('click', event => {
  if (!hasUnsavedPosting()) return;
  event.preventDefault();
  if (typeof cancelDialog.showModal === 'function') cancelDialog.showModal();
  else if (window.confirm(cancelDialog.querySelector('p').textContent)) window.location.assign(cancel.href);
});
document.getElementById('wizard-continue-editing').addEventListener('click', () => cancelDialog.close());
cancelDialog.addEventListener('close', () => cancel.focus({preventScroll: true}));
document.getElementById('property-confirm-leave').addEventListener('click', () => { window.location.assign(cancel.href); });
const completed = new Set();
const approved = new Map();
const sectionSnapshot = section => JSON.stringify([...section.querySelectorAll('input,select,textarea')]
  .filter(control => control.name && !control.disabled)
  .map(control => [control.name, control.type === 'radio' || control.type === 'checkbox' ? control.checked :
    control.type === 'file' ? [...control.files].map(file => [file.name, file.size, file.lastModified]) : control.value]));
function invalidateChangedSection(section) {
  if (!section) return;
  const key = section.dataset.wizardStep;
  if (completed.has(key) && ManazilPropertyWizard.changedSinceAcceptance(approved.get(key), sectionSnapshot(section))) completed.delete(key);
}
const value = name => {
  const controls = [...form.querySelectorAll(`[name="${name}"]`)];
  if (controls[0]?.type === "radio") return controls.find(control => control.checked)?.value || "";
  return controls[0]?.value || "";
};
const choices = () => [value("property_type"), value("transaction_type")];
const flow = () => ManazilPropertyWizard.flow(metadata, ...choices());
let current = "purpose";
let revealed = [];
function updateApplicability() {
  const [type, transaction] = choices();
  const rules = ManazilPropertyWizard.applicability(metadata, type, transaction);
  form.querySelectorAll("[data-field]").forEach(group => {
    const name = group.dataset.field;
    const applicable = !(name in metadata.labels) || (rules[name] && rules[name] !== "inapplicable");
    group.hidden = !applicable;
    group.querySelectorAll("input, select, textarea").forEach(control => {
      control.disabled = !applicable;
      if (rules[name] === "inapplicable") {
        if (control.type === "radio" || control.type === "checkbox") control.checked = false;
        else control.value = "";
      }
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
    edit.addEventListener("click", () => {
      section.querySelector("h2").focus({preventScroll: true});
      section.scrollIntoView({block: "start", behavior: "auto"});
    });
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
function sectionValid(section) {
  return [...section.querySelectorAll("input, select, textarea")]
    .every(control => control.disabled || control.type === "hidden" || control.checkValidity());
}
function reveal(through = null, move = false) {
  updateApplicability();
  const path = flow();
  const valid = Object.fromEntries(path.map(key => [key, sectionValid(sections.find(section => section.dataset.wizardStep === key))]));
  const result = ManazilPropertyWizard.progressive(path, completed, valid, through);
  completed.clear(); result.accepted.forEach(key => completed.add(key));
  const previous = revealed;
  revealed = result.visible;
  current = result.current;
  state.value = current;
  sections.forEach(section => {
    const key = section.dataset.wizardStep;
    section.hidden = !revealed.includes(key);
    const button = section.querySelector('.wizard-continue');
    if (button) button.hidden = !ManazilPropertyWizard.showContinue(key, current) || section.hidden;
    if (completed.has(key)) approved.set(key, sectionSnapshot(section));
  });
  const status = document.getElementById("wizard-status");
  const currentLabel = sections.find(section => section.dataset.wizardStep === current).dataset.stepLabel;
  if (status.textContent !== currentLabel) status.textContent = currentLabel;
  if (revealed.includes("review")) renderReview();
  if (!previous.includes("location") && revealed.includes("location")) {
    document.dispatchEvent(new CustomEvent("property-wizard-section", {detail: "location"}));
  }
  // Keep context: scroll only a newly revealed heading into view, without moving focus.
  const newlyRevealed = revealed.find(key => !previous.includes(key));
  if (move && newlyRevealed) {
    const heading = sections.find(section => section.dataset.wizardStep === newlyRevealed).querySelector("h2");
    if (heading.getBoundingClientRect().bottom > window.innerHeight) {
      heading.scrollIntoView({block: "nearest", behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth"});
    }
  }
}
function advance(section) {
  if (!validate(section)) return;
  completed.add(section.dataset.wizardStep);
  approved.set(section.dataset.wizardStep, sectionSnapshot(section));
  reveal(null, true);
}
sections.forEach(section => {
  section.querySelector(".wizard-continue")?.addEventListener("click", () => advance(section));
});
["transaction_type", "property_type", "property_occupancy"].forEach(name => {
  form.querySelectorAll(`[name="${name}"]`).forEach(control => {
    const select = () => advance(control.closest("[data-wizard-step]"));
    control.addEventListener("click", select);
    control.addEventListener("change", select); // Radio arrow-key changes are also supported.
  });
});
form.addEventListener("input", event => {
  const section = event.target.closest("[data-wizard-step]");
  if (section) { invalidateChangedSection(section); reveal(); }
});
form.addEventListener("change", event => {
  const section = event.target.closest("[data-wizard-step]");
  if (section) { invalidateChangedSection(section); reveal(); }
});
form.addEventListener("keydown", event => {
  if (event.key === "Enter" && event.target.matches("input:not([type=radio]):not([type=file]), select")) {
    const section = event.target.closest("[data-wizard-step]");
    if (section?.querySelector(".wizard-continue")) { event.preventDefault(); advance(section); }
  }
});
form.addEventListener("submit", event => {
  if ((event.submitter?.value || "submit") !== "submit") return;
  updateApplicability();
  for (const key of flow().filter(key => key !== "review")) {
    const section = sections.find(section => section.dataset.wizardStep === key);
    if (!sectionValid(section)) {
      event.preventDefault(); reveal(key); validate(section); return;
    }
    completed.add(key);
  }
  // Enter/programmatic submission cannot skip the explicit final Review action.
  if (!revealed.includes("review")) {
    event.preventDefault(); reveal("review", true);
  }
});
form.classList.add("wizard-enhanced");
updateApplicability();
const initial = form.dataset.initialSection;
if (metadata.original && cancel.dataset.rerendered !== "true") {
  flow().filter(key => key !== "review").forEach(key => {
    if (sectionValid(sections.find(section => section.dataset.wizardStep === key))) completed.add(key);
  });
  reveal();
} else if (cancel.dataset.rerendered === "true") {
  flow().slice(0, Math.max(0, flow().indexOf(initial))).forEach(key => {
    if (sectionValid(sections.find(section => section.dataset.wizardStep === key))) completed.add(key);
  });
  reveal(initial);
} else reveal();
originalSnapshot = cancelSnapshot(); // Initial canonicalization is not a user edit.
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
  invalidateChangedSection(photos.closest('[data-wizard-step]'));
  reveal();
}
photos?.addEventListener("change", updateSelectedPhotos);
if (uploadButton) uploadButton.hidden = !photos?.files.length;

}
}
