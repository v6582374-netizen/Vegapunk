from internagent.prompt_library import prompts as _prompt_library
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import json
import numpy as np

from utils.gemini_utils import call_gemini_with_text_prompt

# --- AGENTREVIEW SPECIFIC CONSTANTS (From role_descriptions.py) ---

SCORE_CALCULATION = {
    10: "This study is among the top 2% of all papers. It is one of the most thorough I have seen. It changed my thinking on this topic. I would fight for it to be accepted",
    8: "This study is among the top 10% of all papers. It provides sufficient support for all of its claims/arguments. Some extra experiments are needed, but not essential. The method is highly original and generalizable to various fields. It deepens the understanding of some phenomenons or lowers the barriers to an existing research direction",
    6: "This study provides sufficient support for its major claims/arguments, some minor points may need extra support or details. The method is moderately original and generalizable to various relevant fields. The work it describes is not particularly interesting and/or novel, so it will not be a big loss if people don’t see it in this conference",
    5: "Some of the main claims/arguments are not sufficiently supported, there are major technical/methodological problems. The proposed method is somewhat original and generalizable to various relevant fields. I am leaning towards rejection, but I can be persuaded if my co-reviewers think otherwise",
    3: "This paper makes marginal contributions",
    1: "This study is not yet sufficiently thorough to warrant publication or is not relevant to the conference",
}

AGENT_REVIEW_RUBRICS = (
    f"* 10: {SCORE_CALCULATION[10]};\n"
    f"* 8: {SCORE_CALCULATION[8]};\n"
    f"* 6: {SCORE_CALCULATION[6]};\n"
    f"* 5: {SCORE_CALCULATION[5]};\n"
    f"* 3: {SCORE_CALCULATION[3]};\n"
    f"* 1: {SCORE_CALCULATION[1]}. "
)

# --- PROMPT GENERATORS ---


def get_agentreview_system_prompt(
    is_knowledgeable=True, is_responsible=True, is_benign=True
):
    """
    Constructs the system prompt based on AgentReview's role_descriptions.py.
    Defaults to the 'Best Case' reviewer (Knowledgeable, Responsible, Benign).
    """
    bio = "You are a reviewer. You write peer review of academic papers by evaluating their technical quality, originality, and clarity.\n\n"

    if is_knowledgeable:
        bio += "Knowledgeability: You are knowledgeable, with a strong background and a PhD degree in the subject areas related to this paper. You possess the expertise necessary to scrutinize and provide insightful feedback to this paper.\n\n"
    else:
        bio += "Knowledgeability: You are not knowledgeable and do not have strong background in the subject areas related to this paper.\n\n"

    if is_responsible:
        bio += "Responsibility: As a responsible reviewer, you highly responsibly write paper reviews. You meticulously assess a research paper's technical accuracy, innovation, and relevance. You thoroughly read the paper, critically analyze the methodologies, and carefully consider the paper's contribution to the field.\n\n"
    else:
        bio += "Responsibility: As a lazy reviewer, your reviews tend to be superficial and hastily done. Your assessments might overlook critical details, lack depth in analysis, fail to recognize novel contributions, or offer generic feedback.\n\n"

    if is_benign:
        bio += "Intention: As a benign reviewer, your approach to reviewing is guided by a genuine intention to aid authors in enhancing their work. You provide detailed, constructive feedback, aimed at both validating robust research and guiding authors to refine and improve their work. You are also critical of technical flaws in the paper.\n\n"
    else:
        bio += "Intention: As a mean reviewer, your reviewing style is often harsh and overly critical, with a tendency towards negative bias. Your reviews may focus excessively on faults, sometimes overlooking the paper's merits.\n\n"

    bio += f"## Rubrics for Overall Rating\n{AGENT_REVIEW_RUBRICS}"

    return bio


# We adapt the instruction form to request JSON but strictly follow AgentReview's content structure.
AGENTREVIEW_INSTRUCTIONS = _prompt_library.get("paper.agent_review.agentreview_instructions")


def perform_review_agentreview(
    text,
    model_name,
    num_review_ensemble=3,
    temperature=0.75,
    reviewer_system_prompt=None,
    review_instruction_form=AGENTREVIEW_INSTRUCTIONS,
):
    print(f"Start paper reviewing using model: `{model_name}`")
    # Generate the "Best Case" AgentReview persona
    if reviewer_system_prompt is None:
        reviewer_system_prompt = get_agentreview_system_prompt(
            is_knowledgeable=True, is_responsible=True, is_benign=True
        )
    base_prompt = review_instruction_form
    base_prompt += f"""
Here is the paper you are asked to review:
```
{text}
```"""

    if num_review_ensemble > 1:
        parsed_reviews = []
        for i in range(num_review_ensemble):
            print(f"Generating ensemble review {i + 1}/{num_review_ensemble}...")
            response = call_gemini_with_text_prompt(
                prompt=base_prompt,
                model_name=model_name,
                generation_configs={
                    "temperature": temperature,
                    "system_instruction": reviewer_system_prompt,
                },
            )
            parsed_reviews.append(response["parsed_response"])
        review = get_meta_review(model_name, temperature, parsed_reviews)
        if review is None:
            review = parsed_reviews[0]
        for score, limits in [
            ("Originality", (1, 4)),
            ("Quality", (1, 4)),
            ("Clarity", (1, 4)),
            ("Significance", (1, 4)),
            ("Soundness", (1, 4)),
            ("Presentation", (1, 4)),
            ("Contribution", (1, 4)),
            ("Overall", (1, 10)),
            ("Confidence", (1, 5)),
        ]:
            scores = []
            for r in parsed_reviews:
                if score in r:
                    try:
                        val = int(r[score])
                        if limits[0] <= val <= limits[1]:
                            scores.append(val)
                    except (ValueError, TypeError):
                        pass
            if scores:
                review[score] = int(round(np.mean(scores)))
    else:
        response = call_gemini_with_text_prompt(
            prompt=base_prompt,
            model_name=model_name,
            generation_configs={
                "temperature": temperature,
                "system_instruction": reviewer_system_prompt,
            },
        )
        review = response["parsed_response"]
    return review


meta_reviewer_system_prompt = _prompt_library.get("paper.agent_review.meta_reviewer_system_prompt")


def get_meta_review(model, temperature, reviews):
    review_text = ""
    for i, r in enumerate(reviews):
        review_text += f"""
Review {i + 1}/{len(reviews)}:
```
{json.dumps(r)}
```
"""
    base_prompt = AGENTREVIEW_INSTRUCTIONS + review_text
    response = call_gemini_with_text_prompt(
        prompt=base_prompt,
        model_name=model,
        generation_configs={
            "temperature": temperature,
            "system_instruction": meta_reviewer_system_prompt.format(
                reviewer_count=len(reviews)
            ),
        },
    )
    meta_review = response["parsed_response"]
    return meta_review
