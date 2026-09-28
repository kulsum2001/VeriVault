/* Applies the saved theme before first paint (loaded synchronously in <head>). */
(function () {
  try {
    var saved = localStorage.getItem("verivault-theme");
    var dark = saved ? saved === "dark" : window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
    document.documentElement.setAttribute("data-theme", dark ? "dark" : "light");
  } catch (e) { /* storage unavailable */ }
})();
