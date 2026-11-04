import {
  COLLECT_LIMIT,
  COLLECT_RESULTS_KEY,
  MESSAGE_TYPES,
  NAVER_AUTO_COLLECT_KEY,
  NAVER_NEWS_ORIGINS,
  THEME_STORAGE_KEY
} from "../shared/constants.js";

const PAGE_SIZE = 50;

const statusNode = document.getElementById("collect-status");
const inFlightNode = document.getElementById("in-flight");
const publisherNode = document.getElementById("publisher");
const closeAfterNode = document.getElementById("close-after");
const openNextNode = document.getElementById("open-next");
const messageNode = document.getElementById("collect-message");
const candidatesNode = document.getElementById("candidates");
const naverAutoNode = document.getElementById("naver-auto");
const openNaverNode = document.getElementById("open-naver");
const naverMessageNode = document.getElementById("naver-message");
const recentNode = document.getElementById("recent");

const STATUS_LABELS = { opening: "여는 중", loading: "분석 중", done: "저장됨", error: "실패" };

let candidates = [];
let collectedByMe = 0;
let results = {};
let loading = null;

async function send(type, payload = {}) {
  const response = await chrome.runtime.sendMessage({ type, payload });
  if (!response?.ok) throw new Error(response?.error || "요청에 실패했습니다.");
  return response.result;
}

async function initialize() {
  const stored = await chrome.storage.local.get([THEME_STORAGE_KEY, NAVER_AUTO_COLLECT_KEY]);
  document.documentElement.dataset.theme = stored[THEME_STORAGE_KEY] === "dark" ? "dark" : "light";
  naverAutoNode.checked = Boolean(stored[NAVER_AUTO_COLLECT_KEY]);
  results = (await chrome.storage.session.get(COLLECT_RESULTS_KEY))[COLLECT_RESULTS_KEY] || {};
  renderRecent();

  const auth = await send(MESSAGE_TYPES.GET_AUTH_STATE).catch(() => null);
  if (!auth?.token) {
    statusNode.textContent = "확장 프로그램 패널에서 먼저 로그인해 주세요. 로그인한 뒤 이 페이지를 새로고침하면 됩니다.";
    openNextNode.disabled = true;
    return;
  }
  await loadCandidates();
}

// The list is always the first page of what is still unanalyzed. Articles this page already
// opened (in progress or failed) are still candidates on the server, so ask for that many extra.
function loadCandidates() {
  if (loading) return loading;
  loading = (async () => {
    messageNode.textContent = "";
    try {
      const data = await send(MESSAGE_TYPES.GET_COLLECT_CANDIDATES, {
        publisher: publisherNode.value || "",
        limit: Math.min(200, PAGE_SIZE + Object.keys(results).length),
        offset: 0
      });
      renderPublishers(data.publishers);
      candidates = data.items.filter((item) => !results[String(item.newsId)]).slice(0, PAGE_SIZE);
      collectedByMe = data.collectedByMe;
      renderCandidates();
      renderStatus();
    } catch (error) {
      messageNode.textContent = error.message;
    } finally {
      loading = null;
    }
  })();
  return loading;
}

// Once every listed article has been opened, fetch the next ones instead of a "더 보기" button.
function refillIfUsedUp() {
  if (candidates.length && !nextCandidate()) void loadCandidates();
}

function renderPublishers(publishers) {
  const selected = publisherNode.value;
  const total = publishers.reduce((sum, item) => sum + item.count, 0);
  const options = [new Option(`전체 (${total.toLocaleString()}건)`, "")];
  for (const { publisher, count } of publishers) {
    options.push(new Option(`${publisher || "언론사 미상"} (${count.toLocaleString()}건)`, publisher));
  }
  publisherNode.replaceChildren(...options);
  publisherNode.value = selected;
}

function renderStatus() {
  statusNode.textContent = `내가 분석해 저장한 기사 ${collectedByMe.toLocaleString()}건`;
  const active = activeCount();
  inFlightNode.textContent = active ? `진행 중 ${active}/${COLLECT_LIMIT}` : "";
  openNextNode.disabled = active >= COLLECT_LIMIT || !nextCandidate();
}

function activeCount() {
  return Object.values(results).filter((result) => result.status === "opening" || result.status === "loading").length;
}

function nextCandidate() {
  return candidates.find((item) => !results[String(item.newsId)]);
}

function renderCandidates() {
  if (!candidates.length) {
    candidatesNode.replaceChildren(stateItem("남은 후보 기사가 없습니다."));
    return;
  }
  candidatesNode.replaceChildren(...candidates.map(candidateItem));
}

function candidateItem(item) {
  const result = results[String(item.newsId)];
  const li = document.createElement("li");
  li.dataset.status = result?.status || "";

  const text = document.createElement("div");
  const meta = document.createElement("div");
  meta.className = "meta";
  meta.textContent = [item.publisher, item.publishedAt].filter(Boolean).join(" ");
  const title = document.createElement("div");
  title.className = "title";
  title.textContent = item.title;
  text.append(meta, title);
  if (result?.status === "error") text.append(errorLine(result.error));

  li.append(text, result && result.status !== "error" ? stateLabel(result) : openButton(item, result));
  return li;
}

function openButton(item, result) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "chip-button";
  button.textContent = result?.status === "error" ? "다시 열기" : "열기";
  button.disabled = activeCount() >= COLLECT_LIMIT;
  button.addEventListener("click", () => void openCandidate(item));
  return button;
}

function stateLabel(result) {
  const label = document.createElement("span");
  label.className = "state";
  label.dataset.status = result.status;
  label.textContent = result.status === "done" && result.cached ? "이미 분석됨" : STATUS_LABELS[result.status] || "";
  return label;
}

function errorLine(message) {
  const line = document.createElement("div");
  line.className = "state";
  line.dataset.status = "error";
  line.textContent = message || "분석에 실패했습니다.";
  return line;
}

function stateItem(message) {
  const li = document.createElement("li");
  li.className = "state-message";
  li.textContent = message;
  return li;
}

// Called straight from a click: the permission prompt only works inside the user's gesture.
async function openCandidate(item) {
  messageNode.textContent = "";
  let origin;
  try {
    origin = `${new URL(item.url).origin}/*`;
  } catch {
    messageNode.textContent = "기사 주소가 올바르지 않습니다.";
    return;
  }
  const granted = await chrome.permissions.request({ origins: [origin] }).catch(() => false);
  if (!granted) {
    messageNode.textContent = `${new URL(item.url).hostname}의 본문 읽기 권한이 필요합니다.`;
    return;
  }
  try {
    await send(MESSAGE_TYPES.COLLECT_OPEN, { newsId: item.newsId, url: item.url, closeAfter: closeAfterNode.checked });
  } catch (error) {
    messageNode.textContent = error.message;
  }
}

function renderRecent() {
  const entries = Object.entries(results)
    .sort(([, a], [, b]) => b.updatedAt.localeCompare(a.updatedAt))
    .slice(0, 20);
  if (!entries.length) {
    recentNode.replaceChildren(stateItem("아직 처리한 기사가 없습니다."));
    return;
  }
  recentNode.replaceChildren(
    ...entries.map(([key, result]) => {
      const li = document.createElement("li");
      li.dataset.status = result.status;
      const text = document.createElement("div");
      const title = document.createElement("div");
      title.className = "title";
      title.textContent = result.title || result.url;
      text.append(title);
      if (result.status === "error") text.append(errorLine(result.error));
      const retry = /^\d+$/.test(key) && result.status === "error" && result.url;
      li.append(text, retry ? openButton({ newsId: Number(key), url: result.url }, result) : stateLabel(result));
      return li;
    })
  );
}

publisherNode.addEventListener("change", () => {
  candidates = [];
  void loadCandidates();
});
openNextNode.addEventListener("click", () => {
  const item = nextCandidate();
  if (item) void openCandidate(item);
});

naverAutoNode.addEventListener("change", async () => {
  naverMessageNode.textContent = "";
  if (!naverAutoNode.checked) {
    await chrome.storage.local.set({ [NAVER_AUTO_COLLECT_KEY]: false });
    return;
  }
  const granted = await chrome.permissions.request({ origins: NAVER_NEWS_ORIGINS }).catch(() => false);
  naverAutoNode.checked = granted;
  await chrome.storage.local.set({ [NAVER_AUTO_COLLECT_KEY]: granted });
  naverMessageNode.textContent = granted
    ? "켜졌습니다. 이제 네이버 뉴스 기사를 열면 자동으로 분석합니다."
    : "네이버 뉴스 본문 읽기 권한이 필요합니다.";
});

openNaverNode.addEventListener("click", () => {
  void chrome.tabs.create({ url: "https://news.naver.com/" });
});

chrome.storage.onChanged.addListener((changes, area) => {
  if (area !== "session" || !changes[COLLECT_RESULTS_KEY]) return;
  const previous = results;
  results = changes[COLLECT_RESULTS_KEY].newValue || {};
  const saved = Object.entries(results).filter(
    ([key, result]) => result.status === "done" && previous[key]?.status !== "done" && !result.cached
  ).length;
  collectedByMe += saved;
  renderCandidates();
  renderRecent();
  renderStatus();
  refillIfUsedUp();
});

void initialize();
