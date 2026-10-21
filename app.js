(function () {
  "use strict";

  var root = document.documentElement;
  var body = document.body;
  var buttons = Array.prototype.slice.call(
    document.querySelectorAll("[data-lang-btn]")
  );

  var titleZh = body.getAttribute("data-title-zh") || document.title;
  var titleEn = body.getAttribute("data-title-en") || titleZh;
  var descZh = body.getAttribute("data-desc-zh") || "";
  var descEn = body.getAttribute("data-desc-en") || descZh;

  var metaDescription = document.querySelector('meta[name="description"]');
  var status = document.getElementById("lang-status");

  function normalize(value) {
    return value === "en" ? "en" : "zh";
  }

  function setLang(lang, options) {
    var next = normalize(lang);
    var opts = options || {};
    var isEn = next === "en";

    root.setAttribute("data-lang", next);
    root.setAttribute("lang", isEn ? "en" : "zh-CN");

    buttons.forEach(function (button) {
      button.setAttribute(
        "aria-pressed",
        String(button.getAttribute("data-lang-btn") === next)
      );
    });

    document.title = isEn ? titleEn : titleZh;
    if (metaDescription) {
      metaDescription.setAttribute("content", isEn ? descEn : descZh);
    }

    if (opts.announce && status) {
      status.textContent = isEn ? "Switched to English" : "已切换到中文";
    }

    try {
      localStorage.setItem("resume.lang", next);
    } catch (error) {
      /* storage may be unavailable; language still switches */
    }

    if (opts.updateUrl) {
      var url = new URL(window.location.href);
      if (isEn) {
        url.searchParams.set("lang", "en");
      } else {
        url.searchParams.delete("lang");
      }
      window.history.replaceState(null, "", url);
    }
  }

  buttons.forEach(function (button) {
    button.addEventListener("click", function () {
      setLang(button.getAttribute("data-lang-btn"), {
        announce: true,
        updateUrl: true
      });
    });
  });

  Array.prototype.forEach.call(
    document.querySelectorAll("[data-print]"),
    function (button) {
      button.addEventListener("click", function () {
        window.print();
      });
    }
  );

  window.addEventListener("storage", function (event) {
    if (event.key === "resume.lang") {
      setLang(event.newValue, { announce: true, updateUrl: false });
    }
  });

  /* Turn on GitHub source links only when the site is served by Pages. */
  /* The owner has not confirmed a public GitHub username yet; set to true later. */
  var SHOW_GITHUB_LINKS = false;
  var host = window.location.hostname;
  if (SHOW_GITHUB_LINKS && /\.github\.io$/i.test(host)) {
    var user = host.split(".")[0];
    var segments = window.location.pathname.split("/").filter(Boolean);
    var repo = segments.length ? segments[0] : user + ".github.io";

    Array.prototype.forEach.call(
      document.querySelectorAll("[data-gh-path]"),
      function (link) {
        link.href =
          "https://github.com/" +
          user +
          "/" +
          repo +
          "/blob/main/" +
          link.getAttribute("data-gh-path");
        link.hidden = false;
      }
    );

    Array.prototype.forEach.call(
      document.querySelectorAll("[data-repo-link]"),
      function (link) {
        link.href = "https://github.com/" + user + "/" + repo;
        link.hidden = false;
      }
    );
  }

  setLang(root.getAttribute("data-lang"), {
    announce: false,
    updateUrl: false
  });
})();
