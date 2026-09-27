"use strict";

const availabilityMode = document.getElementById("availability_mode");
const availabilityDate = document.getElementById("available_from_date");
const dateField = document.querySelector("[data-availability-date]");

function updateAvailabilityDate() {
  const needsDate = availabilityMode.value === "date";
  dateField.hidden = !needsDate;
  availabilityDate.required = needsDate;
}

if (availabilityMode && availabilityDate && dateField) {
  availabilityMode.addEventListener("change", updateAvailabilityDate);
  updateAvailabilityDate();
}
