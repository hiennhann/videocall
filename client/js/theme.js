const root = document.documentElement;
const admin = document.body.classList.contains("admin-page");
const key = admin ? "videocall.admin.theme" : "videocall.theme";
const preference = matchMedia("(prefers-color-scheme: dark)");

function render(theme) {
  root.dataset.theme = theme;
  const dark = theme === "dark";
  for (const button of document.querySelectorAll("[data-theme-toggle]")) {
    button.setAttribute("aria-pressed", String(dark));
    button.textContent = dark ? "Giao diện sáng" : "Giao diện tối";
  }
}

function sync() {
  const stored = localStorage.getItem(key);
  render(stored === "dark" || (!stored && preference.matches) ? "dark" : "light");
}

document.addEventListener("click", event => {
  if (!event.target.closest?.("[data-theme-toggle]")) return;
  const theme = root.dataset.theme === "dark" ? "light" : "dark";
  localStorage.setItem(key, theme);
  render(theme);
});
document.addEventListener("htmx:afterSwap", sync);
window.addEventListener("storage", event => { if (event.key === key) sync(); });
preference.addEventListener("change", sync);
sync();

export function applyBranding(config) {
  if (!config) return;
  if (config.project_name) {
    for (const label of document.querySelectorAll("[data-project-name]")) {
      label.textContent = config.project_name;
    }
    document.title = document.title.replace(/Videocall$/, () => config.project_name);
  }
  if (["system", "serif", "monospace"].includes(config.brand_font)) {
    root.dataset.brandFont = config.brand_font;
  }
  if (!/^#[0-9a-f]{6}$/i.test(config.brand_color)) return;
  const rgb = config.brand_color.slice(1).match(/../g).map(part => parseInt(part, 16) / 255);
  const linear = rgb.map(value => value <= .04045 ? value / 12.92 : ((value + .055) / 1.055) ** 2.4);
  const luminance = linear[0] * .2126 + linear[1] * .7152 + linear[2] * .0722;
  root.style.setProperty("--accent", config.brand_color);
  root.style.setProperty("--accent-ink", luminance > .179 ? "#000" : "#fff");
}
