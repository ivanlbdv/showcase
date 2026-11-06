(() => {
  const CONSENT_KEY = "finparus_cookie_consent";
  const CONSENT_MAX_AGE = 180 * 24 * 60 * 60 * 1000;

  const banner = document.querySelector("#cookie-banner");

  if (!banner) return;

  const getConsent = () => {
    try {
      const saved = JSON.parse(localStorage.getItem(CONSENT_KEY));

      if (!saved || !saved.date) return null;

      if (Date.now() - saved.date > CONSENT_MAX_AGE) {
        localStorage.removeItem(CONSENT_KEY);
        return null;
      }

      return saved.value;
    } catch {
      return null;
    }
  };

  const saveConsent = (value) => {
    localStorage.setItem(
      CONSENT_KEY,
      JSON.stringify({
        value,
        date: Date.now()
      })
    );
  };

  const loadMetrika = () => {
    if (window.ym) return;

    (function (m, e, t, r, i, k, a) {
      m[i] = m[i] || function () {
        (m[i].a = m[i].a || []).push(arguments);
      };
      m[i].l = 1 * new Date();

      for (let j = 0; j < document.scripts.length; j++) {
        if (document.scripts[j].src === r) return;
      }

      k = e.createElement(t);
      a = e.getElementsByTagName(t)[0];
      k.async = 1;
      k.src = r;
      a.parentNode.insertBefore(k, a);
    })(
      window,
      document,
      "script",
      "https://mc.yandex.ru/metrika/tag.js?id=113804707",
      "ym"
    );

    ym(113804707, "init", {
      ssr: true,
      webvisor: true,
      clickmap: true,
      ecommerce: "dataLayer",
      referrer: document.referrer,
      url: location.href,
      accurateTrackBounce: true,
      trackLinks: true
    });
  };

  const showBanner = () => {
    banner.hidden = false;
  };

  const hideBanner = () => {
    banner.hidden = true;
  };

  const applyConsent = (value) => {
    saveConsent(value);
    hideBanner();

    if (value === "accepted") {
      loadMetrika();
    }
  };

  banner.querySelectorAll("[data-cookie-choice]").forEach((button) => {
    button.addEventListener("click", () => {
      applyConsent(button.dataset.cookieChoice);
    });
  });

  const consent = getConsent();

  if (consent === "accepted") {
    loadMetrika();
  } else if (consent !== "rejected") {
    showBanner();
  }

  document.querySelectorAll("[data-cookie-settings]").forEach((link) => {
    link.addEventListener("click", (event) => {
      event.preventDefault();
      showBanner();
    });
  });
})();
