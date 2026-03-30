export type SelectedNodeRect = {
  top: number
  left: number
  width: number
  height: number
}

export type SelectedNodeContext = {
  tagName: string
  textPreview: string
  role: string | null
  ariaLabel: string | null
  id: string | null
  classList: string[]
  dataBtomsId: string | null
  boundingRect: SelectedNodeRect
  parentSummary: string | null
  sectionSummary: string | null
  suggestedSelector: string | null
}

const PREVIEW_SELECTION_MESSAGE_SOURCE = 'btoms-preview-selection'
const PREVIEW_SELECTION_BRIDGE_IMPORT = `import "/src/__btoms_selection_bridge.js";`
const PREVIEW_SELECTION_BRIDGE_PATH = '/src/__btoms_selection_bridge.js'

function formatBtomsIdLabel(value: string) {
  return value
    .split(/[-_]/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')
}

export function describeSelectedNode(selection: SelectedNodeContext | null) {
  if (!selection) {
    return ''
  }

  if (selection.dataBtomsId) {
    return formatBtomsIdLabel(selection.dataBtomsId)
  }

  const textPreview = selection.textPreview.trim()
  if (textPreview) {
    return textPreview.length > 42 ? `${textPreview.slice(0, 42)}...` : textPreview
  }

  if (selection.ariaLabel) {
    return selection.ariaLabel
  }

  if (selection.id) {
    return `#${selection.id}`
  }

  return `<${selection.tagName.toLowerCase()}>`
}

function buildSelectionBridgeModule(selectionModeEnabled: boolean) {
  return `const SOURCE = "${PREVIEW_SELECTION_MESSAGE_SOURCE}";
const STATE_KEY = "__btomsPreviewSelectionState";
const OVERLAY_ID = "__btoms_selection_overlay__";
const TARGET_SELECTOR = [
  "[data-btoms-id]",
  "button",
  "a",
  "input",
  "textarea",
  "select",
  "label",
  "h1",
  "h2",
  "h3",
  "h4",
  "h5",
  "h6",
  "p",
  "span",
  "li",
  "img",
  "picture",
  "video",
  "section",
  "article",
  "aside",
  "nav",
  "header",
  "footer",
  "main",
  "[role='button']",
  "[role='link']",
  "[role='textbox']",
  "[role='tab']",
  "[role='option']"
].join(",");

function inferRole(element) {
  const explicitRole = element.getAttribute("role");
  if (explicitRole) return explicitRole;
  const tagName = element.tagName.toLowerCase();
  if (tagName === "button") return "button";
  if (tagName === "a" && element.getAttribute("href")) return "link";
  if (tagName === "input") return "input";
  if (tagName === "textarea") return "textbox";
  if (tagName === "select") return "select";
  return null;
}

function summarizeElement(element) {
  if (!element) return null;
  const dataBtomsId = element.getAttribute("data-btoms-id");
  if (dataBtomsId) return dataBtomsId;
  const ariaLabel = element.getAttribute("aria-label");
  if (ariaLabel) return ariaLabel;
  const text = (element.textContent || "").replace(/\\s+/g, " ").trim();
  if (text) return text.slice(0, 80);
  const id = element.getAttribute("id");
  if (id) return "#" + id;
  const className = Array.from(element.classList || []).slice(0, 2).join(".");
  return className ? element.tagName.toLowerCase() + "." + className : element.tagName.toLowerCase();
}

function findSectionSummary(element) {
  const section = element.closest("section, article, aside, nav, header, footer, main, [data-btoms-id]");
  return summarizeElement(section);
}

function buildSuggestedSelector(element) {
  const dataBtomsId = element.getAttribute("data-btoms-id");
  if (dataBtomsId) return '[data-btoms-id="' + dataBtomsId.replace(/"/g, '\\\\\\"') + '"]';
  const id = element.getAttribute("id");
  if (id) return "#" + id.replace(/"/g, '\\\\\\"');
  const classList = Array.from(element.classList || []).filter(Boolean).slice(0, 2);
  if (classList.length > 0) return element.tagName.toLowerCase() + "." + classList.join(".");
  return element.tagName.toLowerCase();
}

function buildPayload(element) {
  const rect = element.getBoundingClientRect();
  return {
    tagName: element.tagName,
    textPreview: (element.textContent || "").replace(/\\s+/g, " ").trim().slice(0, 140),
    role: inferRole(element),
    ariaLabel: element.getAttribute("aria-label"),
    id: element.getAttribute("id"),
    classList: Array.from(element.classList || []).slice(0, 8),
    dataBtomsId: element.getAttribute("data-btoms-id"),
    boundingRect: {
      top: rect.top,
      left: rect.left,
      width: rect.width,
      height: rect.height,
    },
    parentSummary: summarizeElement(element.parentElement),
    sectionSummary: findSectionSummary(element),
    suggestedSelector: buildSuggestedSelector(element),
  };
}

function createOverlay() {
  let overlay = document.getElementById(OVERLAY_ID);
  if (overlay) return overlay;
  overlay = document.createElement("div");
  overlay.id = OVERLAY_ID;
  overlay.style.position = "fixed";
  overlay.style.zIndex = "2147483647";
  overlay.style.pointerEvents = "none";
  overlay.style.border = "2px solid rgba(255, 176, 98, 0.95)";
  overlay.style.borderRadius = "14px";
  overlay.style.boxShadow = "0 0 0 1px rgba(255, 235, 207, 0.45), inset 0 0 0 1px rgba(255, 214, 165, 0.18)";
  overlay.style.background = "transparent";
  overlay.style.opacity = "0";
  overlay.style.transition = "opacity 120ms ease";
  document.body.appendChild(overlay);
  return overlay;
}

function getState() {
  const state = window[STATE_KEY];
  if (state) return state;
  const nextState = {
    mode: ${selectionModeEnabled ? 'true' : 'false'},
    selectedElement: null,
    hoveredElement: null,
    overlay: createOverlay(),
  };
  window[STATE_KEY] = nextState;
  return nextState;
}

function hideOverlay() {
  getState().overlay.style.opacity = "0";
}

function showOverlay(element) {
  const rect = element.getBoundingClientRect();
  if (rect.width <= 0 || rect.height <= 0) {
    hideOverlay();
    return;
  }
  const overlay = getState().overlay;
  overlay.style.opacity = "1";
  overlay.style.top = rect.top + "px";
  overlay.style.left = rect.left + "px";
  overlay.style.width = rect.width + "px";
  overlay.style.height = rect.height + "px";
}

function isSelectableElement(element) {
  if (!(element instanceof HTMLElement)) return false;
  if (element === document.body || element === document.documentElement) return false;
  const tagName = element.tagName.toLowerCase();
  return tagName !== "script" && tagName !== "style";
}

function resolveSelectableTarget(target) {
  if (!(target instanceof HTMLElement)) return null;
  const exactMatch = target.closest(TARGET_SELECTOR);
  if (exactMatch && isSelectableElement(exactMatch)) {
    return exactMatch;
  }
  return isSelectableElement(target) ? target : null;
}

function swallowEvent(event) {
  event.preventDefault();
  event.stopPropagation();
  if (typeof event.stopImmediatePropagation === "function") {
    event.stopImmediatePropagation();
  }
}

function handlePointerMove(event) {
  const state = getState();
  if (!state.mode) {
    hideOverlay();
    return;
  }
  const element = resolveSelectableTarget(event.target);
  if (!element || !isSelectableElement(element)) {
    state.hoveredElement = null;
    hideOverlay();
    return;
  }
  state.hoveredElement = element;
  showOverlay(element);
}

function handlePointerDown(event) {
  const state = getState();
  if (!state.mode) return;
  const element = resolveSelectableTarget(event.target);
  if (!element || !isSelectableElement(element)) return;
  swallowEvent(event);
  state.selectedElement = element;
  hideOverlay();
  window.parent.postMessage({
    source: SOURCE,
    type: "node-selected",
    payload: buildPayload(element),
  }, "*");
}

function handleBlockedEvent(event) {
  const state = getState();
  if (!state.mode) return;
  swallowEvent(event);
}

if (!window.__BTOMS_SELECTION_BRIDGE_INSTALLED__) {
  window.__BTOMS_SELECTION_BRIDGE_INSTALLED__ = true;
  document.addEventListener("pointermove", handlePointerMove, true);
  document.addEventListener("pointerdown", handlePointerDown, true);
  document.addEventListener("click", handleBlockedEvent, true);
  document.addEventListener("mousedown", handleBlockedEvent, true);
  document.addEventListener("mouseup", handleBlockedEvent, true);
  document.addEventListener("touchstart", handleBlockedEvent, true);
  document.addEventListener("touchend", handleBlockedEvent, true);
  document.addEventListener("pointerleave", hideOverlay, true);
  window.addEventListener("blur", hideOverlay);
  window.addEventListener("message", (event) => {
    const data = event.data;
    if (!data || data.source !== SOURCE || data.type !== "selection-mode") return;
    const state = getState();
    state.mode = Boolean(data.enabled);
    if (!state.mode) {
      hideOverlay();
    }
  });
}
`
}

function findMainEntryPath(files: Record<string, string>) {
  const candidates = ['/src/main.ts', '/src/main.js', '/src/main.jsx', '/src/main.tsx']
  return candidates.find((candidate) => candidate in files) ?? null
}

export function buildPreviewWorkspaceFiles(
  files: Record<string, string>,
  selectionModeEnabled: boolean,
) {
  const mainEntryPath = findMainEntryPath(files)
  if (!mainEntryPath) {
    return files
  }

  const nextFiles = { ...files }
  const mainEntry = nextFiles[mainEntryPath] ?? ''
  if (!mainEntry.includes(PREVIEW_SELECTION_BRIDGE_IMPORT)) {
    nextFiles[mainEntryPath] = `${PREVIEW_SELECTION_BRIDGE_IMPORT}\n${mainEntry}`
  }

  nextFiles[PREVIEW_SELECTION_BRIDGE_PATH] = buildSelectionBridgeModule(selectionModeEnabled)
  return nextFiles
}
