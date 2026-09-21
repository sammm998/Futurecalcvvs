const test = require('node:test');
const assert = require('node:assert/strict');
const {context, scopeOf, methodOf, resultName} = require('../vectorascore/static/assignment-context.js');

test('assignment feedback describes the loaded result', () => {
  const result = {assignmentMethod:'llm', binding_mode:'astra'};
  const c = context(result, 'bindings');
  assert.equal(c.scope, 'llm');
  assert.equal(c.name, 'LLM · Astra');
  assert.match(c.detail, /this LLM · Astra result/);
});

test('vector and OCR tabs remain shared even when the source analysis used LLM', () => {
  for (const tab of ['pipes','nodes','leaders','labels']) {
    assert.equal(scopeOf({tab, assignmentMethod:'llm'}), 'shared');
    assert.equal(scopeOf({tab, assignmentMethod:'dimension'}), 'shared');
  }
});

test('historical modes are recovered without inventing a method for previews or missing metadata', () => {
  assert.equal(methodOf({binding_mode:'flow'}), 'dimension');
  assert.equal(methodOf({binding_mode:'astra'}), 'llm');
  assert.equal(scopeOf({tab:'bindings',binding_mode:'preview'}), 'preview');
  assert.equal(scopeOf({tab:'bindings'}), 'unknown');
  assert.equal(resultName({}), 'Method not recorded');
});

test('snapshots retain their provenance in read-only review', () => {
  const c = context({assignmentMethod:'dimension'}, 'bindings', true);
  assert.equal(c.scope, 'dimension');
  assert.match(c.detail, /read only/);
});
