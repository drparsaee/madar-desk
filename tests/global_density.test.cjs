'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const postcss = require('postcss');

const css = postcss.parse(fs.readFileSync(path.join(__dirname, '../src/styles.css'), 'utf8'));
function declaration(selector, property, media = null) {
  const matches = [];
  css.walkRules(rule => {
    if (!rule.selectors?.includes(selector)) return;
    const context = rule.parent.type === 'atrule' ? rule.parent.params : null;
    if (context !== media) return;
    rule.walkDecls(property, decl => matches.push(decl.value));
  });
  return matches.at(-1);
}
function px(selector, property, media = null) {
  const value = declaration(selector, property, media);
  assert.match(value ?? '', /^\d+px$/, `${selector} must set ${property} in pixels`);
  return Number.parseInt(value, 10);
}

test('app layout uses compact spacing without sacrificing card readability', () => {
  assert.ok(px('.sidebar', 'width') <= 232);
  assert.ok(px('.topbar', 'height') <= 64);
  assert.ok(px('.stat-card', 'min-height') <= 110);
  assert.ok(px('.stat-card', 'min-height') >= 96);
  assert.ok(px('.dialog-head', 'height') <= 58);
  assert.ok(px('.task-card', 'min-height') >= 36);
  assert.match(declaration('.task-title', 'line-height'), /^1\.[5-9]/);
  assert.equal(declaration('.kanban', 'min-height'), '0', 'board has no artificial empty vertical area');
});

test('icon controls retain at least 32px targets and primary controls 36px', () => {
  for (const selector of ['.sidebar-plus', '.lane-add', '.stage-drag-handle', '.top-icon']) {
    assert.ok(px(selector, 'min-height') >= 32, `${selector}: small target`);
    assert.ok(px(selector, 'min-width') >= 32, `${selector}: narrow target`);
  }
  assert.ok(px('.sidebar-nav button', 'min-height') >= 36);
  assert.ok(px('.board-tabs button', 'min-height') >= 36);
  assert.ok(px('.btn', 'min-height') >= 36);
});

test('narrow viewports keep navigation and lists accessible, never hiding actions', () => {
  let responsive = 0;
  css.walkAtRules('media', media => {
    if (!/max-width:\s*(?:860|850|600)px/.test(media.params)) return;
    responsive += 1;
    media.walkRules(rule => {
      rule.walkDecls('display', decl => {
        if (decl.value !== 'none') return;
        for (const selector of rule.selectors || []) {
          assert.ok(
            !/\.sidebar-settings|\.sidebar-nav\s+button(?!\s+span)|\.top-actions\s*>\s*\.top-icon|\.list-row\s*>\s*span/.test(selector),
            `interactive action or list data hidden at ${media.params}: ${selector}`,
          );
        }
      });
    });
  });
  assert.ok(responsive >= 3);
  assert.equal(declaration('.top-actions', 'overflow-x', '(max-width:600px)'), 'auto');
  assert.equal(declaration('.list-mode', 'overflow-x', '(max-width:600px)'), 'auto');
  assert.ok(px('.sidebar-plus', 'width', '(max-width:860px)') >= 32);
});
