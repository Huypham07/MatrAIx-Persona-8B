"""Prompt templates for Hierarchical Attribute Dependency Extraction."""

SYSTEM_PROMPT = """You are an expert Persona Attribute Analyst in an AI Persona Simulation System (MatrAIx Persona).
Your mission is to analyze survey questions and determine which persona traits/dimensions from a structured taxonomy
causally or statistically influence how an individual persona will answer that survey question in the given context.

You must be precise, analytical, and avoid selecting irrelevant branches or attributes.
Always respond in valid JSON format.
"""

LAYER_1_FILTER_PROMPT = """You are analyzing the dependency of a survey question on high-level persona trait groups.
{context_text}
### Survey Question:
\"{question_text}\"
{options_text}

### Candidate Layer 1 Groups (Top-level Taxonomy):
{candidates_text}

### Task:
Select which Layer 1 Groups contain persona attributes that could meaningfully influence or correlate with how a persona responds to this question.
Prune groups that are completely unrelated or irrelevant.

### Response format (JSON only):
{{
  "selected_ids": ["group_id_1", "group_id_2"],
  "reasoning": "Brief explanation of why these top-level groups were selected."
}}
"""

LAYER_2_FILTER_PROMPT = """You are refining attribute dependencies down to Layer 2 Subgroups under the parent group: '{parent_label}' ({parent_id}).
{context_text}
### Survey Question:
\"{question_text}\"
{options_text}

### Candidate Layer 2 Subgroups under '{parent_label}':
{candidates_text}

### Task:
Select the subgroups that are likely to contain specific traits influencing the answer to this survey question.
Prune subgroups that are irrelevant.

### Response format (JSON only):
{{
  "selected_ids": ["subgroup_id_1", "subgroup_id_2"],
  "reasoning": "Brief explanation of why these subgroups were selected."
}}
"""

LAYER_3_FILTER_PROMPT = """You are refining attribute dependencies down to Layer 3 Categories under the subgroup: '{parent_label}' ({parent_id}).
{context_text}
### Survey Question:
\"{question_text}\"
{options_text}

### Candidate Layer 3 Categories under '{parent_label}':
{candidates_text}

### Task:
Select the specific categories that are most directly relevant to this survey question.
Prune categories that do not directly affect the response.

### Response format (JSON only):
{{
  "selected_ids": ["category_id_1", "category_id_2"],
  "reasoning": "Brief explanation of why these categories were selected."
}}
"""

LAYER_4_DIMENSIONS_PROMPT = """You are selecting the exact leaf Persona Dimensions (Attributes) under the category: '{parent_label}' ({parent_id}).
{context_text}
### Survey Question:
\"{question_text}\"
{options_text}

### Candidate Dimensions in this Category:
{candidates_text}

### Task:
Select ONLY the dimensions that realistically impact, dictate, or bias how a persona responds to this survey question.
For each selected dimension:
1. Provide a concise 'reasoning' explaining the causal/behavioral mechanism (how this trait affects the answer).
2. Assign 'relevance_strength': 'high' (direct determinant) or 'medium' (moderate influence). Do not select low/negligible traits.

### Response format (JSON only):
{{
  "selected_attributes": [
    {{
      "id": "dimension_id",
      "reasoning": "Why this specific attribute influences the answer.",
      "relevance_strength": "high"
    }}
  ],
  "reasoning": "Summary of selection rationale."
}}
"""

