// 딥이: an ink drop holding a magnifier. Static markup with no user data, so innerHTML is safe here.
// Parts carry classes (m-eyes, m-arm-wave, m-lens …) that panel.css animates per data-state.
const MASCOT_SVG = `
<svg class="mascot-svg" viewBox="0 0 140 128" xmlns="http://www.w3.org/2000/svg" focusable="false">
  <ellipse class="m-shadow" cx="64" cy="119" rx="26" ry="4" />
  <g class="m-figure">
    <g class="m-arm-wave">
      <path class="m-limb" d="M35 80 Q21 74 19 61" />
      <circle class="m-ink" cx="19" cy="58" r="5.5" />
    </g>
    <path class="m-ink" d="M64 10 C64 10 30 48 30 74 A34 34 0 0 0 98 74 C98 48 64 10 64 10 Z" />
    <ellipse class="m-shine" cx="49" cy="58" rx="4.5" ry="9" transform="rotate(-22 49 58)" />
    <g class="m-eyes">
      <ellipse class="m-eye" cx="54" cy="75" rx="6.5" ry="7.5" />
      <ellipse class="m-eye" cx="76" cy="75" rx="6.5" ry="7.5" />
      <g class="m-pupils">
        <circle cx="55" cy="76" r="3.4" />
        <circle cx="77" cy="76" r="3.4" />
      </g>
    </g>
    <ellipse class="m-cheek" cx="46" cy="87" rx="5" ry="3" />
    <ellipse class="m-cheek" cx="84" cy="87" rx="5" ry="3" />
    <path class="m-mouth" d="M59 87 Q65 93 71 87" />
    <g class="m-lens">
      <path class="m-limb" d="M95 84 Q106 86 107 94" />
      <circle class="m-glass" cx="111" cy="101" r="11" />
      <path class="m-glint" d="M104 97 Q106 93 110 92" />
      <path class="m-limb" d="M119 109 L127 117" />
    </g>
  </g>
</svg>`;

export function mountMascots(root = document) {
  for (const node of root.querySelectorAll("[data-mascot]")) {
    if (!node.firstElementChild) node.innerHTML = MASCOT_SVG;
  }
}

const typingRuns = new WeakMap();

// Types text into node one character at a time; a newer call on the same node cancels the older one.
export async function typeText(node, text, { instant = false, delay = 65 } = {}) {
  if (!node) return false;
  const run = Symbol("typing");
  typingRuns.set(node, run);
  if (instant) {
    node.textContent = text;
    return true;
  }

  node.textContent = "";
  for (const character of text) {
    if (typingRuns.get(node) !== run) return false;
    node.textContent += character;
    await wait(delay);
  }
  return typingRuns.get(node) === run;
}

export function wait(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}
