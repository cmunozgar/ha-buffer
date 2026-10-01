// Registers the "buffer:" icon set so `buffer:logo` can be used anywhere
// Home Assistant accepts an icon (dashboards, entities, the sidebar).
const VIEWBOX = "0 0 512 512";
const ICONS = {
  logo:
    "M255 2L480 117L255 232L30 117Z" +
    "M30 254L100 219L255 296L410 219L480 254L255 367Z" +
    "M30 389L100 351L255 434L410 351L480 389L255 510Z",
};

window.customIcons = window.customIcons || {};
window.customIcons.buffer = {
  getIcon: async (name) =>
    ICONS[name] ? { path: ICONS[name], viewBox: VIEWBOX } : undefined,
  getIconList: async () =>
    Object.keys(ICONS).map((name) => ({ name, keywords: ["buffer"] })),
};
