import { beforeEach, describe, expect, it } from 'vitest';
import i18n from './i18n';

describe('review stillReachable pluralization', () => {
  beforeEach(async () => {
    await i18n.changeLanguage('en');
  });

  it('resolves pluralized English review labels', () => {
    expect(i18n.t('review.stillReachable', { count: 1 })).toBe(
      'This memory is still reachable via 1 other path:',
    );
    expect(i18n.t('review.stillReachable', { count: 2 })).toBe(
      'This memory is still reachable via 2 other paths:',
    );
  });

  it('resolves zh-CN review labels without falling back to raw keys', async () => {
    await i18n.changeLanguage('zh-CN');
    expect(i18n.t('review.stillReachable', { count: 2 })).toBe(
      '这条记忆仍可通过另外 2 条路径访问：',
    );
  });

  it('resolves maintenance delete labels with english singular/plural grammar', async () => {
    await i18n.changeLanguage('en');
    expect(i18n.t('maintenance.deleteOrphans', { count: 1 })).toBe(
      'Delete 1 orphan',
    );
    expect(i18n.t('maintenance.deleteOrphans', { count: 2 })).toBe(
      'Delete 2 orphans',
    );
    expect(i18n.t('maintenance.prompts.deleteMemories', { count: 1 })).toBe(
      'Permanently delete 1 memory? This cannot be undone.',
    );
    expect(i18n.t('maintenance.prompts.deleteMemories', { count: 2 })).toBe(
      'Permanently delete 2 memories? This cannot be undone.',
    );
  });

  it('resolves maintenance delete labels in zh-CN without raw key fallback', async () => {
    await i18n.changeLanguage('zh-CN');
    expect(i18n.t('maintenance.deleteOrphans', { count: 1 })).toBe(
      '删除 1 条孤儿记忆',
    );
    expect(i18n.t('maintenance.prompts.deleteMemories', { count: 1 })).toBe(
      '确认永久删除 1 条记忆吗？此操作无法撤销。',
    );
  });
});
