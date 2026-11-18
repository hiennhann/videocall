export function icon(name) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.classList.add("icon");
  svg.setAttribute("aria-hidden", "true");
  const use = document.createElementNS(svg.namespaceURI, "use");
  use.setAttribute("href", `/client/icons/sprite.svg#${name}`);
  svg.append(use);
  return svg;
}

export function setAvatar(node, userId, name) {
  let hash = 0;
  for (const char of String(userId)) hash = (hash * 31 + char.codePointAt(0)) >>> 0;
  node.dataset.tone = String(hash % 5);
  const words = name.normalize("NFC").trim().split(/\s+/u).filter(Boolean);
  const initials = words.length > 1 ? [words[0], words.at(-1)] : words;
  node.textContent = initials.map(word => Array.from(word)[0]).join("").toLocaleUpperCase("vi");
  node.setAttribute("role", "img");
  node.setAttribute("aria-label", name);
}

export function initDialogs(root = document) {
  for (const trigger of root.querySelectorAll("[data-dialog]")) {
    trigger.addEventListener("click", () => {
      const dialog = document.getElementById(trigger.dataset.dialog);
      trigger.focus();
      dialog.showModal();
    });
  }
  for (const dialog of root.querySelectorAll("dialog")) {
    for (const close of dialog.querySelectorAll("[data-close]")) {
      close.addEventListener("click", () => dialog.close());
    }
    // Native showModal() makes the rest of the document inert and handles Esc.
    // Wrap Tab explicitly so focus never moves into the browser chrome.
    dialog.addEventListener("keydown", event => {
      if (event.key !== "Tab") return;
      const targets = Array.from(dialog.querySelectorAll("button:not(:disabled), a[href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex='0']"));
      const first = targets[0];
      const last = targets.at(-1);
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    });
  }
}

export function initTabs(root = document) {
  for (const list of root.querySelectorAll("[role='tablist']")) {
    const tabs = Array.from(list.querySelectorAll("[role='tab']"));
    function select(tab) {
      for (const item of tabs) {
        const active = item === tab;
        item.setAttribute("aria-selected", String(active));
        item.tabIndex = active ? 0 : -1;
        document.getElementById(item.getAttribute("aria-controls")).hidden = !active;
      }
    }
    tabs.forEach((tab, index) => {
      tab.addEventListener("click", () => select(tab));
      tab.addEventListener("keydown", event => {
        const offsets = { ArrowRight: 1, ArrowLeft: -1 };
        if (!(event.key in offsets) && event.key !== "Home" && event.key !== "End") return;
        event.preventDefault();
        const next = event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : (index + offsets[event.key] + tabs.length) % tabs.length;
        tabs[next].focus();
        select(tabs[next]);
      });
    });
  }
}

export function initDropdowns(root = document) {
  for (const dropdown of root.querySelectorAll("details.dropdown")) {
    dropdown.addEventListener("keydown", event => {
      if (event.key === "Escape" && dropdown.open) {
        event.preventDefault();
        dropdown.open = false;
        dropdown.querySelector("summary").focus();
      }
    });
    root.addEventListener("click", event => {
      if (!dropdown.contains(event.target)) dropdown.open = false;
    });
  }
}
