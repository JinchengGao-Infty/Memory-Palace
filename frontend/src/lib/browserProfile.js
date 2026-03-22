export const DEFAULT_BROWSER_PROFILE = 'default';
export const EDGE_BROWSER_PROFILE = 'edge';

const EDGE_USER_AGENT_PATTERN = /\bEdg(?:A|iOS)?\//i;

const brandLooksLikeEdge = (brand) =>
  typeof brand === 'string' && brand.trim().toLowerCase().includes('edge');

export const detectBrowserProfile = (nav = globalThis.navigator) => {
  if (!nav || typeof nav !== 'object') {
    return DEFAULT_BROWSER_PROFILE;
  }

  const brands = Array.isArray(nav.userAgentData?.brands) ? nav.userAgentData.brands : [];
  if (brands.some((entry) => brandLooksLikeEdge(entry?.brand))) {
    return EDGE_BROWSER_PROFILE;
  }

  const userAgent = typeof nav.userAgent === 'string' ? nav.userAgent : '';
  if (EDGE_USER_AGENT_PATTERN.test(userAgent)) {
    return EDGE_BROWSER_PROFILE;
  }

  return DEFAULT_BROWSER_PROFILE;
};

export const isEdgeBrowserProfile = (nav = globalThis.navigator) =>
  detectBrowserProfile(nav) === EDGE_BROWSER_PROFILE;

export const applyBrowserProfileAttribute = (
  doc = globalThis.document,
  nav = globalThis.navigator
) => {
  const profile = detectBrowserProfile(nav);
  const root = doc?.documentElement;

  if (root?.dataset) {
    root.dataset.browserProfile = profile;
  }

  return profile;
};
