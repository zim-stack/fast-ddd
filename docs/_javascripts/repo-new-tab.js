// Open the repository link in the header in a new tab.
// document$ is provided by Material for MkDocs and fires on every
// page load, including instant navigation, so the attribute is re-applied.
document$.subscribe(function () {
  document.querySelectorAll("a.md-source").forEach(function (link) {
    link.setAttribute("target", "_blank");
    link.setAttribute("rel", "noopener");
  });
});
