// Tallyo Client Main Script

// Theme Initialization
(function initTheme() {
  const saved = localStorage.getItem("tallyo_theme") || "light";
  document.documentElement.setAttribute("data-theme", saved);
})();

function toggleTheme() {
  const current = document.documentElement.getAttribute("data-theme") || "light";
  const next = current === "dark" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next);
  localStorage.setItem("tallyo_theme", next);
}

// Toast Notifications
function showToast(message, type = "info") {
  let container = document.getElementById("toast-container");
  if (!container) {
    container = document.createElement("div");
    container.id = "toast-container";
    document.body.appendChild(container);
  }

  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `
    <span>${message}</span>
  `;

  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transform = "translateY(10px)";
    toast.style.transition = "all 0.2s ease";
    setTimeout(() => toast.remove(), 200);
  }, 3200);
}

// Copy to Clipboard
function copyToClipboard(text, label = "Item") {
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(() => {
      showToast(`${label} copied to clipboard`, "success");
    }).catch(() => {
      fallbackCopy(text, label);
    });
  } else {
    fallbackCopy(text, label);
  }
}

function fallbackCopy(text, label) {
  const input = document.createElement("input");
  input.value = text;
  document.body.appendChild(input);
  input.select();
  document.execCommand("copy");
  input.remove();
  showToast(`${label} copied to clipboard`, "success");
}

// Modals
function openModal(id) {
  const modal = document.getElementById(id);
  if (modal) {
    modal.classList.add("open");
    document.body.style.overflow = "hidden";
  }
}

function closeModal(id) {
  const modal = document.getElementById(id);
  if (modal) {
    modal.classList.remove("open");
    document.body.style.overflow = "";
  }
}

// Slide-overs
function openSlideover(id) {
  const panel = document.getElementById(id);
  const backdrop = document.getElementById(id + "-backdrop");
  if (panel) panel.classList.add("open");
  if (backdrop) backdrop.classList.add("open");
}

function closeSlideover(id) {
  const panel = document.getElementById(id);
  const backdrop = document.getElementById(id + "-backdrop");
  if (panel) panel.classList.remove("open");
  if (backdrop) backdrop.classList.remove("open");
}

// Mobile Sidebar
function toggleMobileSidebar() {
  const sidebar = document.querySelector(".app-sidebar");
  if (sidebar) {
    sidebar.classList.toggle("open");
  }
}

// Command Palette Navigation Index
const PALETTE_ROUTES = [
  { title: "Billing Overview", url: "/app", category: "App" },
  { title: "Subscription Plans", url: "/app/plans", category: "App" },
  { title: "Usage & Metering", url: "/app/usage", category: "App" },
  { title: "Usage Credits & Top-Up", url: "/app/credits", category: "App" },
  { title: "Invoices & Receipts", url: "/app/invoices", category: "App" },
  { title: "Payment Methods", url: "/app/payment-methods", category: "App" },
  { title: "Workspace Settings", url: "/app/settings", category: "App" },
  { title: "Developer API & Simulation Clock", url: "/app/developers", category: "App" },
  { title: "Pricing & Plans", url: "/pricing", category: "Public" },
  { title: "API Documentation", url: "/docs", category: "Public" },
  { title: "Customer Stories", url: "/customers", category: "Public" },
  { title: "Platform Changelog", url: "/changelog", category: "Public" },
  { title: "Platform Status", url: "/status", category: "Public" },
  { title: "Operator Console", url: "/admin", category: "Operator" },
];

function openCommandPalette() {
  const backdrop = document.getElementById("cmd-palette-backdrop");
  if (!backdrop) return;
  backdrop.classList.add("open");
  const input = document.getElementById("cmd-search-input");
  if (input) {
    input.value = "";
    input.focus();
    renderPaletteItems("");
  }
}

function closeCommandPalette() {
  const backdrop = document.getElementById("cmd-palette-backdrop");
  if (backdrop) backdrop.classList.remove("open");
}

function renderPaletteItems(query) {
  const container = document.getElementById("cmd-results");
  if (!container) return;
  const q = query.toLowerCase().trim();
  const filtered = PALETTE_ROUTES.filter(r => r.title.toLowerCase().includes(q) || r.category.toLowerCase().includes(q));

  if (filtered.length === 0) {
    container.innerHTML = `<div style="padding:16px;text-align:center;color:var(--text-muted);">No matching destinations found</div>`;
    return;
  }

  container.innerHTML = filtered.map((item, idx) => `
    <a href="${item.url}" class="cmd-item ${idx === 0 ? 'selected' : ''}">
      <span>${item.title}</span>
      <span class="cmd-item-category">${item.category}</span>
    </a>
  `).join("");
}

// Global Keyboard Listeners
document.addEventListener("keydown", (e) => {
  // Command + K or Ctrl + K
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
    e.preventDefault();
    const backdrop = document.getElementById("cmd-palette-backdrop");
    if (backdrop && backdrop.classList.contains("open")) {
      closeCommandPalette();
    } else {
      openCommandPalette();
    }
  }

  // Escape closes modals and palette
  if (e.key === "Escape") {
    closeCommandPalette();
    document.querySelectorAll(".modal-backdrop.open").forEach(m => m.classList.remove("open"));
    document.querySelectorAll(".slideover-panel.open").forEach(s => s.classList.remove("open"));
    document.querySelectorAll(".slideover-backdrop.open").forEach(b => b.classList.remove("open"));
    document.body.style.overflow = "";
  }
});
