import { translate } from "./app/i18n/vi.js";

const root = document.documentElement;
const admin = document.body.classList.contains("admin-page");
const key = admin ? "videocall.admin.theme" : "videocall.theme";
const preference = matchMedia("(prefers-color-scheme: dark)");
let inMemoryTheme;

function storedTheme() {
  if (inMemoryTheme) return inMemoryTheme;
  try { return localStorage.getItem(key); } catch { return null; }
}

function sync() {
  translate();
  const stored = storedTheme();
  const choice = ["light", "dark", "system"].includes(stored) ? stored : admin ? "dark" : "light";
  const theme = choice === "system" ? (preference.matches ? "dark" : "light") : choice;
  root.dataset.theme = theme;
  for (const select of document.querySelectorAll("[data-theme-select]")) select.value = choice;
  for (const button of document.querySelectorAll("[data-theme-toggle]")) {
    button.setAttribute("aria-pressed", String(theme === "dark"));
    button.textContent = theme === "dark" ? "Giao diện sáng" : "Giao diện tối";
  }
}

function saveTheme(theme) {
  try { localStorage.setItem(key, theme); } catch { inMemoryTheme = theme; }
  sync();
}
document.addEventListener("change", event => {
  if (event.target.matches("[data-theme-select]")) saveTheme(event.target.value);
});
document.addEventListener("click", event => {
  if (event.target.closest?.("[data-theme-toggle]")) saveTheme(root.dataset.theme === "dark" ? "light" : "dark");
});
document.addEventListener("htmx:afterSwap", () => { sync(); if (admin) loadAdminBranding(); });
window.addEventListener("storage", event => { if (event.key === key) sync(); });
preference.addEventListener("change", sync);
sync();

export function applyBranding(config) {
  if (!config) return;
  if (config.project_name) {
    for (const label of document.querySelectorAll("[data-project-name]")) label.textContent = config.project_name;
    document.title = document.title.replace(/Videocall$/, () => config.project_name);
  }
  if (["system", "serif", "monospace"].includes(config.brand_font)) root.dataset.brandFont = config.brand_font;
  if (!/^#[0-9a-f]{6}$/i.test(config.brand_color)) return;
  const defaultColor = getComputedStyle(root).getPropertyValue("--brand-default").trim().toLowerCase();
  if (config.brand_color.toLowerCase() === defaultColor) {
    for (const token of ["--primary", "--primary-hover", "--on-primary"]) root.style.removeProperty(token);
    return;
  }
  const rgb = config.brand_color.slice(1).match(/../g).map(part => parseInt(part, 16) / 255);
  const linear = rgb.map(value => value <= .04045 ? value / 12.92 : ((value + .055) / 1.055) ** 2.4);
  const luminance = linear[0] * .2126 + linear[1] * .7152 + linear[2] * .0722;
  root.style.setProperty("--primary", config.brand_color);
  root.style.setProperty("--primary-hover", config.brand_color);
  root.style.setProperty("--on-primary", `var(${luminance > .179 ? "--brand-ink-dark" : "--brand-ink-light"})`);
}

async function loadAdminBranding() {
  try {
    const response = await fetch("/api/v1/config/public");
    if (response.ok) applyBranding(await response.json());
  } catch { /* The administration pages remain usable when public config is unavailable. */ }
}
if (admin) loadAdminBranding();
