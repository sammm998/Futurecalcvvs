/* Feedback describes the displayed result, never a pending generation job. */
(() => {
  const methodOf = record => {
    const m = record?.assignmentMethod || ({astra:'llm', flow:'dimension'})[record?.binding_mode];
    return ['llm', 'dimension'].includes(m) ? m : null;
  };
  const resultName = record => methodOf(record) === 'llm' ? 'LLM · Astra'
    : methodOf(record) === 'dimension' ? 'Dimension'
    : record?.binding_mode === 'preview' ? 'Vector preview' : 'Method not recorded';
  const scopeOf = record => record?.tab === 'bindings' || record?.track === 'binding'
    ? methodOf(record) || (record?.binding_mode === 'preview' ? 'preview' : 'unknown') : 'shared';
  const scopeName = record => ({shared:'Shared feedback', dimension:'Dimension assignments',
    llm:'LLM assignments', preview:'Preview assignments', unknown:'Assignment method unknown'})[scopeOf(record)];
  const context = (metadata, tab, readonly = false) => {
    const record = {...metadata, tab};
    const actual = methodOf(metadata);
    const name = resultName(metadata);
    const assignment = tab === 'bindings';
    return {actual, name, scope:scopeOf(record), title:scopeName(record),
      detail: readonly ? 'Saved analysis · read only. This result keeps its original method.'
        : !metadata ? 'Select a processed drawing to capture feedback.'
        : assignment ? `Feedback is saved against this ${name} result.`
        : `Corrections to vectors and label reading support both methods. Captured from: ${name}.`};
  };
  const api = {methodOf, resultName, scopeOf, scopeName, context};
  if (typeof window !== 'undefined') window.AssignmentContext = api;
  if (typeof module !== 'undefined') module.exports = api;
})();
