// Cross-browser (Chrome service worker / Firefox event page).
const ext = globalThis.browser ?? globalThis.chrome;
const DASH = "https://ds.shipwrights.dev";

// The dashboard session cookie is HttpOnly, so only the background can read it.
// It is sent to the Clanker API as a bearer token purely so the API can check it is a
// live session with Dashboard access. It is never stored.
async function getToken() {
  const cookie = await ext.cookies.get({ url: DASH, name: "session" });
  return cookie ? cookie.value : null;
}

ext.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg && msg.type === "getToken") {
    getToken().then((token) => sendResponse({ token }), () => sendResponse({ token: null }));
    return true; // async response
  }
});

ext.action.onClicked.addListener(() => {
  ext.tabs.create({ url: ext.runtime.getURL("judgements.html") });
});
