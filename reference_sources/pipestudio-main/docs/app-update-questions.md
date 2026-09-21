# Questions from the AI rebuilding Pipe Studio

See the [complete expert workflow and learning levels](feedback-workflow.md) and
[global-first validation policy](global-first-learning.md) for context.

The rebuilding AI writes its own clarification questions. Pipe Studio persists and
displays them; it does not generate a second AI reply or automatically start a
coding agent when the expert answers.

1. Read `GET /api/studio/implementation-brief?id=REQUEST_ID`. Existing conversations
   contain expert answers. Do not ask again for information already provided.
2. If the intended business outcome is unclear, post a question to
   `POST /api/studio/implementation-questions`:

```json
{
  "id": "REQUEST_ID",
  "feedback_id": "LINKED_OPEN_FEEDBACK_ID",
  "reason": "Clarify the intended grouping before changing the algorithm.",
  "questions": [{
    "question": "I understand these sections should stay separate. Is that what you mean, or should they form one continuous pipe?",
    "impact": "Keeping them separate preserves individual elements. Joining them produces one continuous run.",
    "options": ["Keep separate pipes", "Use one continuous pipe"]
  }]
}
```

Prefer one supportive question. Reflect your understanding, propose an
interpretation and invite correction. Explain practical consequences grounded in
the evidence. Use the expert's language. Do not ask for tolerances, graph topology,
implementation details or a technical solution. Options are optional; free text
is always accepted. Do not invent commercial, quantity or safety consequences.

3. Pause dependent implementation work until the expert answers. Other independent
   work can continue. No answer can be inferred from elapsed time.
4. Read the same brief when continuing. The answer is in `conversations`, linked by
   `reply_to` to the question. Studio does not wake an external coding agent.
5. Implement and validate the clarified behavior under the global-first policy,
   then attach results with `POST /api/studio/implementation-result`.

Questions and answers stay in **App updates**, on the original feedback thread.
An unanswered question blocks attaching and accepting results. Sending an answer
neither publishes a rule nor reruns Improvements nor archives the feedback. The
request stays open until validated results are accepted. Its full conversation is
retained in Feedback archive afterwards.
