# Survey Product Feedback

We're gathering reactions to **FocusLoop**, a family coordination app concept.

Read the product brief, then complete every question in the questionnaire. We want to know how you'd price it, whether you'd try it, and how it would fit into household life — not feature ideas outside the brief.

## How to answer

- Read the brief before you start.
- Answer every required question.
- For multiple-choice, use the listed option ids.
- For rating scales, use a whole number in the given range.
- Give the answer alone unless a question also asks for a short reason or confidence.

## Files (container runs)

When you run inside the task container (working directory `/app`), the survey
form is not delivered turn-by-turn — read and write it yourself:

- Questionnaire (question ids, types, option ids, scale ranges): `/app/input/questionnaire.yaml`
- Product brief: `/app/input/context.md`
- Write your completed survey to `/app/output/survey_result.json`:

```json
{
  "answers": [
    {"questionId": "<id>", "prompt": "<question text>", "value": "<option id | number | text>", "rationale": "<short reason>"}
  ],
  "trajectory": [
    {
      "timestamp": "<ISO-8601>",
      "actor": "persona",
      "action": "ask_question",
      "context": {"questionId": "<id>", "questionType": "<single_choice|multi_choice|likert|free_text>"},
      "outcome": {"answered": true}
    }
  ]
}
```

Add one `ask_question` trajectory event per answered question — every event
needs all five keys (`timestamp`, `actor`, `action`, `context`, `outcome`;
`context` and `outcome` are objects), with `questionType` copied from the
questionnaire's `type` field.
