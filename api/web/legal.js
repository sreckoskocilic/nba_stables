(function () {
  const CONSENT_KEY = "nbastables_analytics_consent";
  const WEBSITE_ID = "b68bfbcf-f86b-4e65-9257-bda61e465ddb";
  const SCRIPT_SRC = "/t/a.js";

  function consentValue() {
    return localStorage.getItem(CONSENT_KEY);
  }

  function ensureAnalyticsScript() {
    if (document.querySelector('script[data-website-id="' + WEBSITE_ID + '"]')) {
      return;
    }
    const script = document.createElement("script");
    script.defer = true;
    script.src = SCRIPT_SRC;
    script.setAttribute("data-website-id", WEBSITE_ID);
    document.body.appendChild(script);
  }

  function showBanner() {
    const banner = document.getElementById("cookieBanner");
    if (banner) {
      banner.style.display = "flex";
    }
  }

  function hideBanner() {
    const banner = document.getElementById("cookieBanner");
    if (banner) {
      banner.style.display = "none";
    }
  }

  function setConsent(value) {
    localStorage.setItem(CONSENT_KEY, value);
    hideBanner();
    if (value === "accepted") {
      ensureAnalyticsScript();
    }
  }

  function initBanner() {
    const acceptBtn = document.getElementById("cookieAccept");
    const rejectBtn = document.getElementById("cookieReject");

    if (acceptBtn) {
      acceptBtn.addEventListener("click", function () {
        setConsent("accepted");
      });
    }

    if (rejectBtn) {
      rejectBtn.addEventListener("click", function () {
        setConsent("rejected");
      });
    }

    const initial = consentValue();
    if (initial === "accepted") {
      ensureAnalyticsScript();
      hideBanner();
      return;
    }

    if (initial === "rejected") {
      hideBanner();
      return;
    }

    showBanner();
  }

  window.openCookieSettings = function () {
    localStorage.removeItem(CONSENT_KEY);
    showBanner();
  };

  // Delegated handler — inline onclick is blocked by the page CSP (script-src 'self').
  document.addEventListener("click", function (event) {
    const trigger = event.target.closest('[data-action="openCookieSettings"]');
    if (trigger) {
      event.preventDefault();
      window.openCookieSettings();
    }
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initBanner);
  } else {
    initBanner();
  }
})();
