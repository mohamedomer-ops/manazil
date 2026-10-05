"use strict";

const mapElement = document.getElementById("property-location-map");
if (mapElement && window.L) {
  const latitude = document.getElementById("latitude");
  const longitude = document.getElementById("longitude");
  const clearButton = document.getElementById("clear-property-location");
  const selected = [Number(latitude.value), Number(longitude.value)];
  const hasLocation = latitude.value !== "" && longitude.value !== "" &&
    Number.isFinite(selected[0]) && Number.isFinite(selected[1]) &&
    Math.abs(selected[0]) <= 90 && Math.abs(selected[1]) <= 180;
  const map = L.map(mapElement, {
    scrollWheelZoom: false,
    dragging: !window.matchMedia("(pointer: coarse)").matches,
  }).setView(hasLocation ? selected : [15.5, 30.2], hasLocation ? 14 : 5);
  document.addEventListener('property-wizard-section', event => {
    if (event.detail === 'location') requestAnimationFrame(() => map.invalidateSize());
  });
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  }).addTo(map);

  let marker = hasLocation ? L.marker(selected).addTo(map) : null;
  clearButton.hidden = !marker;
  function selectLocation(position) {
    latitude.value = position.lat.toFixed(6);
    longitude.value = position.lng.toFixed(6);
    if (marker) marker.setLatLng(position);
    else marker = L.marker(position).addTo(map);
    clearButton.hidden = false;
  }
  map.on("click", event => selectLocation(event.latlng));
  mapElement.addEventListener("keydown", event => {
    if (event.target === mapElement && (event.key === "Enter" || event.key === " ")) {
      event.preventDefault();
      selectLocation(map.getCenter());
    }
  });
  clearButton.addEventListener("click", () => {
    latitude.value = "";
    longitude.value = "";
    if (marker) map.removeLayer(marker);
    marker = null;
    clearButton.hidden = true;
  });
}
