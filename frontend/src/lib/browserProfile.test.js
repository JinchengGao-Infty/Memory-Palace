import { describe, expect, it } from 'vitest';

import {
  EDGE_BROWSER_PROFILE,
  DEFAULT_BROWSER_PROFILE,
  applyBrowserProfileAttribute,
  detectBrowserProfile,
  isEdgeBrowserProfile,
} from './browserProfile';

describe('browser profile detection', () => {
  it('detects Edge from userAgentData brands', () => {
    const profile = detectBrowserProfile({
      userAgentData: {
        brands: [{ brand: 'Chromium' }, { brand: 'Microsoft Edge' }],
      },
      userAgent: 'Mozilla/5.0',
    });

    expect(profile).toBe(EDGE_BROWSER_PROFILE);
    expect(isEdgeBrowserProfile({
      userAgentData: {
        brands: [{ brand: 'Microsoft Edge' }],
      },
    })).toBe(true);
  });

  it('detects Edge from legacy userAgent fallback', () => {
    expect(
      detectBrowserProfile({
        userAgent:
          'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/135.0.0.0 Safari/537.36 Edg/135.0.0.0',
      })
    ).toBe(EDGE_BROWSER_PROFILE);
  });

  it('returns default for non-Edge browsers and syncs the html data attribute', () => {
    const doc = { documentElement: { dataset: {} } };
    const profile = applyBrowserProfileAttribute(doc, {
      userAgent:
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/135.0.0.0 Safari/537.36',
    });

    expect(profile).toBe(DEFAULT_BROWSER_PROFILE);
    expect(doc.documentElement.dataset.browserProfile).toBe(DEFAULT_BROWSER_PROFILE);
  });
});
