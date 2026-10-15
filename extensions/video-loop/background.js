// A shortcut grants activeTab, so these scripts run only in the tab that was in front
// when it was pressed, and only then. The extension has no other access to any site.
//
// State is shown with marks in the tab title, which Zyraena reads from Opera's window
// title: LOOP while the video loops, VOLUME while waiting for a number / right after
// the volume changed.
chrome.commands.onCommand.addListener(async (command, tab) => {
  const handlers = { "toggle-loop": [toggleLoop, "ISOLATED"], "set-volume": [askVolume, "MAIN"] };
  const [func, world] = handlers[command] || [];
  if (!func) return;
  const target = tab ?? (await chrome.tabs.query({ active: true, currentWindow: true }))[0];
  if (!target?.id) return;
  // The volume script runs in the page's own world so it can use YouTube's player API.
  await chrome.scripting.executeScript({ target: { tabId: target.id }, func, world });
});

// Runs inside the page. Loops the playing video the same way YouTube's right-click
// "Loop" does, and keeps the loop mark in the title while it loops.
function toggleLoop() {
  const MARK = "\u{1F501} ";
  const videos = [...document.querySelectorAll("video")];
  const video =
    document.querySelector("video.html5-main-video") ||
    videos.find((v) => !v.paused) ||
    videos.find((v) => v.duration > 0) ||
    videos[0];
  if (!video) return;

  video.loop = !video.loop;

  // Sites rewrite the title when the video changes; keep the mark in sync with the
  // loop state of the video until looping is turned off.
  const sync = () => {
    const looping = video.isConnected && video.loop;
    const marked = document.title.includes(MARK);
    if (looping && !marked) document.title = MARK + document.title;
    if (!looping && marked) document.title = document.title.replace(MARK, "");
  };
  window.__zyraenaLoopObserver?.disconnect();
  window.__zyraenaLoopObserver = null;
  sync();
  if (video.loop) {
    const observer = new MutationObserver(sync);
    observer.observe(document.querySelector("title") || document.head, {
      childList: true, characterData: true, subtree: true,
    });
    window.__zyraenaLoopObserver = observer;
  }
}

// Runs inside the page (main world). Waits a few seconds for a number typed on the
// keyboard (0-100, then Enter; Esc cancels) and sets the video's volume to it. The
// keys are swallowed so the page's own shortcuts (YouTube: digits seek) don't fire.
function askVolume() {
  const MARK = "\u{1F50A}";
  const TIMEOUT_MS = 5000;
  const SHOW_RESULT_MS = 3000;
  const clearMark = () => {
    document.title = document.title.replace(new RegExp(MARK + "\\S* ", "u"), "");
  };
  const setMark = (text) => {
    clearMark();
    document.title = `${MARK}${text} ` + document.title;
  };

  window.__zyraenaVolumeCancel?.();
  let digits = "";
  const box = document.createElement("div");
  box.style.cssText =
    "position:fixed;top:16px;left:50%;transform:translateX(-50%);z-index:2147483647;" +
    "background:rgba(10,12,20,.92);color:#7df9ff;border:1px solid #7df9ff;border-radius:8px;" +
    "padding:8px 16px;font:600 18px system-ui,sans-serif;pointer-events:none";
  const show = (text) => { box.textContent = text; };
  show("Volume: _");
  document.documentElement.appendChild(box);
  setMark("...");

  const finish = (volume) => {
    window.removeEventListener("keydown", onKey, true);
    clearTimeout(timer);
    window.__zyraenaVolumeCancel = null;
    if (volume === null) {
      box.remove();
      clearMark();
      return;
    }
    const player = document.getElementById("movie_player");
    if (player && typeof player.setVolume === "function") {
      player.setVolume(volume);
      if (volume > 0) player.unMute?.(); else player.mute?.();
    } else {
      const video = [...document.querySelectorAll("video")].find((v) => !v.paused) || document.querySelector("video");
      if (video) {
        video.volume = volume / 100;
        video.muted = volume === 0;
      }
    }
    show(`Volume: ${volume}%`);
    setMark(`${volume}%`);
    setTimeout(() => { box.remove(); clearMark(); }, SHOW_RESULT_MS);
  };

  const onKey = (event) => {
    event.preventDefault();
    event.stopImmediatePropagation();
    if (/^[0-9]$/.test(event.key) && digits.length < 3) {
      digits += event.key;
      show(`Volume: ${digits}_`);
    } else if (event.key === "Backspace") {
      digits = digits.slice(0, -1);
      show(`Volume: ${digits}_`);
    } else if (event.key === "Enter") {
      finish(digits ? Math.min(100, parseInt(digits, 10)) : null);
    } else if (event.key === "Escape") {
      finish(null);
    }
  };

  window.addEventListener("keydown", onKey, true);
  const timer = setTimeout(() => finish(null), TIMEOUT_MS);
  window.__zyraenaVolumeCancel = () => finish(null);
}
