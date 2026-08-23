# Search and choose a laptop from DuckDuckGo

Read the scenario brief in `input/context.md`. Start by formulating a realistic search query on DuckDuckGo based on your persona, browse the search results, visit relevant product/review pages, compare specifications, and pick a laptop you'd seriously consider.

Save your choice to `/app/output/laptop_choice.json`:

```json
{
  "decision_subject_id": "<stable slug or site id for the chosen laptop>",
  "decision_subject_label": "<product title exactly as shown>",
  "decision_outcome": "selected",
  "basis_primary": "<price|quality|features|convenience|taste|trust|familiarity|novelty|fit|other>",
  "exploration_style": "<quick_pick|compared_multiple|deep_research|hesitant>",
  "reason": "<why this laptop matched you>",
  "task_price_text": "<price exactly as shown, e.g. $739.99>"
}
```

Requirements:

- `decision_subject_id` can be a simple slug derived from the title if the page does not expose a cleaner id.
- `basis_primary` should reflect the main factor behind your choice.
- Keep `reason` specific to the selected laptop and what mattered to you.

No login or purchase is required.
