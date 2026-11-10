document.addEventListener("DOMContentLoaded", () => {
  const el = document.getElementById("map");
  if (!el || typeof L === "undefined") {
    if (el) el.innerHTML = '<div style="padding:24px;color:#536176;font-size:13px">Map library could not load. Check your internet connection.</div>';
    return;
  }

  const map = L.map("map").setView([30.195, 71.475], 12);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19, attribution: '&copy; OpenStreetMap contributors'
  }).addTo(map);
  const colors = {High:"#e4565e", Medium:"#e4a52c", Low:"#28aa7c"};
  const points = (window.reliefItems || []).filter(x => x.lat !== null && x.lng !== null);
  points.forEach(item => {
    const color = colors[item.priority] || "#3268e8";
    L.circleMarker([item.lat, item.lng], {radius:9, color, fillColor:color, fillOpacity:.85, weight:2})
      .addTo(map).bindPopup(`<b>Request #${item.id}</b><br>${item.need}<br>${item.location}<br>Priority: ${item.priority}<br>Status: ${item.status}`);
  });
  if (points.length) map.fitBounds(points.map(x => [x.lat, x.lng]), {padding:[25,25], maxZoom:13});
});
