// Calls to the Shipwrights dashboard API, made from the dashboard page with the reviewer's own session
// (same-origin, cookies). Used by the cert-page panel (video upload) and by the nav.js bridge that backs the
// Clanker page's "Reject the project". Nothing here ever goes through the Clanker server.
(() => {
  const JSON_HEADERS = { "Content-Type": "application/json" };
  const base = (slug, id) => `/api/v1/workplaces/${slug}/certifications/${id}`;

  async function call(path, init) {
    const res = await fetch(path, init);
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(body.error || `Dashboard error ${res.status}`);
    return body;
  }

  // The same three steps the dashboard's own upload button performs.
  async function uploadVideo(slug, id, blob, onProgress = () => {}) {
    const file = new File([blob], `${id}.mp4`, { type: "video/mp4" });
    const url = `${base(slug, id)}/upload`;
    onProgress("Uploading video…");
    const q = new URLSearchParams({ filename: file.name, contentType: "video/mp4", size: String(file.size) });
    const { uploadUrl, publicUrl } = await call(`${url}?${q}`);
    const put = await fetch(uploadUrl, { method: "PUT", headers: { "Content-Type": "video/mp4" }, body: file });
    if (!put.ok) throw new Error(`upload failed: ${put.status}`);
    await call(url, { method: "POST", headers: JSON_HEADERS, body: JSON.stringify({ url: publicUrl }) });
  }

  async function status(slug, id) {
    const d = await call(base(slug, id));
    return {
      status: d.status, claimer: d.claimer, claimerId: d.claimerId, viewerIsClaimer: !!d.viewerIsClaimer,
      viewerIsGlobalAdmin: !!d.viewerIsGlobalAdmin, proofVideoUrl: d.proofVideoUrl, feedbackRequired: !!d.feedbackRequired,
    };
  }

  // Reject through the real flow: claim (if needed) -> attach video (optional) -> submit a REJECTED review.
  async function reject({ slug, id, comment, video }, onProgress = () => {}) {
    comment = String(comment || "").trim();
    if (!comment) throw new Error("Write some feedback for the shipper first.");
    if (comment.length > 5000) throw new Error("Feedback is over the 5000 character limit.");
    const d = await status(slug, id);
    if (d.status === "APPROVED" || d.status === "REJECTED") throw new Error(`Already ${d.status.toLowerCase()} on the dashboard.`);
    let claimed = false;
    try {
      if (d.status !== "IN_REVIEW") {
        onProgress("Claiming the ship…");
        await call(`${base(slug, id)}/claim`, { method: "POST", headers: JSON_HEADERS, body: JSON.stringify({ unclaim: false }) });
        claimed = true;
      } else if (!d.viewerIsClaimer && !d.viewerIsGlobalAdmin) {
        const who = d.claimer?.name || d.claimer?.username || "someone else";
        throw new Error(`Already claimed by ${who}.`);
      }
      if (video) await uploadVideo(slug, id, video, onProgress);
      onProgress("Submitting the review…");
      await call(`${base(slug, id)}/review`, { method: "POST", headers: JSON_HEADERS, body: JSON.stringify({ verdict: "REJECTED", comment }) });
    } catch (e) {
      throw new Error(claimed ? `${e.message} (the ship is claimed by you but not rejected yet.)` : e.message);
    }
    return { status: "REJECTED" };
  }

  globalThis.ClankerDash = { uploadVideo, status, reject };
})();
