"""LLM prompt templates for content condensing.

Three-level prompt structure:
1. SYSTEM_PROMPT: General instructions, not specific to video or aggressiveness
2. STRATEGY_PROMPTS: Level-specific instructions (one for each aggressiveness 1-10)
3. USER_PROMPT: Contains the transcript and target word count
"""

# ==============================================================================
# TARGET RETENTION PERCENTAGES - Single source of truth
# ==============================================================================

# Target retention percentages (geometric progression from 75 to 10)
TARGET_RETENTION = {
    1: 75,   # 25% reduction, range 70-80%
    2: 60,   # 40% reduction, range 55-65%
    3: 50,   # 50% reduction, range 45-55%
    4: 38,   # 62% reduction, range 33-43%
    5: 30,   # 70% reduction, range 25-35%
    6: 25,   # 75% reduction, range 20-30%
    7: 20,   # 80% reduction, range 15-25%
    8: 16,   # 84% reduction, range 11-21%
    9: 13,   # 87% reduction, range 8-18%
    10: 10,  # 90% reduction, range 5-15%
}

# ==============================================================================
# LEVEL 1: SYSTEM PROMPT - General instructions
# ==============================================================================

CONDENSE_SYSTEM_PROMPT = """
You are a professional editor specializing in condensing transcripts — preserving the speaker's voice when possible,
and distilling core arguments when brevity demands it.

Your task is to condense a video transcript while preserving all key insights and maintaining natural speech flow.
This is different from summarization; think of it like abridging a book. The reader should feel like they
are reading the original author's words.

**What can always be CUT:**
- Tangents, personal anecdotes that don't support the main points
  (e.g., how this recipe came to be; the history of science from Aristotle to the discovery;
  the speaker's personal journey to discovering the topic)
- Redundant examples that illustrate the same concept multiple times
- Supporting details that are interesting but not essential to the core insights

**What should be PRESERVED:**
- Unique key insights and main arguments
- Essential context needed to understand the above
- Logical transitions between topics
- Critical examples that clarify complex concepts
- Conclusions and takeaways
- The speaker's voice, personality, and speaking style
  Don't substitute less technical or less formal terminology if the speaker uses such

**Constraints:**
1. The condensed script should sound natural when spoken aloud
2. Maintain coherent narrative flow with smooth transitions
3. Preserve the speaker's voice, personality, and speaking style even when paraphrasing
4. Keep the content engaging and easy to follow

**Important: Hit the target word count**
It's important to approach the specified target word count, and not over-condense. Some source content
is incredibly verbose and redundant and could stand to be condensed tremendously without losing information,
but if the user only asks for a conservative reduction, then you should aim for that target word count.

Conversely, for some content, valuable information will have to be lost to meet the user's desired reduction;
Honor the user's desired target word count, and do your best to preserve the most important insights within
that word count constraint.

Do not try to adapt your condensation aggressiveness to the information density of the source content.
Instead, honor the user's target word counts, and do your best to preserve the most
important insights within that constraint.

**Output Instructions:**

Generate a JSON response with the following structure:
{{
  "condensed_script": "The full condensed script formatted naturally for speech. IMPORTANT: Format the script with paragraph breaks (using \\n\\n) at natural topic transitions and logical breaks. Each paragraph should cover a cohesive idea or topic. This makes the script easier to read and more natural when spoken.",
  "key_points_preserved": [
    "First key point or insight preserved",
    "Second key point or insight preserved",
    "Third key point or insight preserved"
  ],
  "removed_content_summary": "Brief description of what types of content were removed",
  "quality_notes": "Any notes about the condensation quality or challenges encountered"
}}

Don't forget to ESCAPE quotation marks in the condensed_script to ensure valid JSON output. TY.

Remember to format the condensed_script with paragraph breaks (\\n\\n) at natural transitions.
"""

# ==============================================================================
# LEVEL 2: STRATEGY PROMPTS - Aggressiveness-specific instructions (1-10)
# ==============================================================================

STRATEGY_PROMPTS = {
    1: """
**Aggressiveness Level 1: Conservative (70-80% retention)**

Your goal is to remove only obvious 'filler' material. Keep almost all content intact.

**Approach:**
- Retain entire passages from the original transcript verbatim whenever possible
- Think like editing a movie: you can take out scenes, but you can't change what the actors say
- Only cut: obvious filler words/phrases, clear tangents, redundant repetitions
- Preserve: all examples, all explanations, speaker's exact phrasing and personality
- Do NOT paraphrase unless absolutely necessary

**Priority:** Preserve the speaker's voice and natural flow above all else.
""",

    2: """
**Aggressiveness Level 2: Light (65-75% retention)**

Remove filler and some repetitive statements. Preserve detailed examples.

**Approach:**
- Mostly retain passages verbatim with selective cuts
- Cut: filler, obvious repetitions, minor tangents
- Preserve: all important examples, detailed explanations, speaker's voice
- Minimal paraphrasing - only when it clearly improves flow without losing meaning
- Keep the speaker's personality and speaking style intact

**Priority:** Keep content nearly complete while removing obvious redundancy.
""",

    3: """
**Aggressiveness Level 3: Gentle (60-70% retention)**

Remove filler, repetitions, and tangents. Keep most examples.

**Approach:**
- Mix of verbatim retention and strategic cuts
- Cut: all filler, repetitions, tangents, less critical anecdotes
- Preserve: most examples, key explanations, logical flow, speaker's voice
- Light paraphrasing acceptable to improve flow
- Maintain natural speech patterns

**Priority:** Clean up the content while keeping the speaker's voice recognizable.
""",

    4: """
**Aggressiveness Level 4: Moderate-Light (55-65% retention)**

Remove filler, repetitions, tangents, and less important examples.

**Approach:**
- Balance between verbatim retention and paraphrasing
- Cut: filler, repetitions, tangents, secondary examples, some elaborations
- Preserve: key examples, main arguments, essential context, core personality
- Moderate paraphrasing to tighten content
- Keep logical transitions

**Priority:** Focus on main content while maintaining readability and flow.
""",

    5: """
**Aggressiveness Level 5: Moderate (45-55% retention)**

Standard condensation. Remove all filler, repetitions, tangents, and keep only key examples.

**Approach:**
- Balanced mix of cuts and paraphrasing
- Cut: all filler, repetitions, tangents, secondary examples, minor details
- Preserve: key examples, core insights, main arguments, essential context
- Use paraphrasing freely to condense while preserving meaning
- Maintain logical flow and key transitions

**Priority:** Capture the essential content while significantly reducing length.
""",

    6: """
**Aggressiveness Level 6: Moderate-Aggressive (40-50% retention)**

Keep only core insights and essential examples. Remove most elaborations.

**Approach:**
- Heavy use of paraphrasing and cutting
- Cut: all filler, most examples, elaborations, supporting details
- Preserve: core insights, essential examples, main arguments
- Paraphrase aggressively to condense
- Some loss of natural flow acceptable to meet word count

**Priority:** Extract core content; speaker's voice becomes secondary to insights.
""",

    7: """
**Aggressiveness Level 7: Aggressive (35-45% retention)**

Focus on main arguments and key insights. Minimal examples, only if critical.

**Approach:**
- Primarily paraphrasing with strategic cuts
- Cut: everything except main arguments, key insights, critical examples
- Preserve: main arguments, unique insights, essential context only
- Heavy paraphrasing required
- Logical flow important but not at cost of word count

**Priority:** Distill to main arguments and insights; natural flow sacrificed if needed.
""",

    8: """
**Aggressiveness Level 8: Very Aggressive (30-40% retention)**

Extract only the most important insights. Very minimal context.

**Approach:**
- Maximum paraphrasing, minimal verbatim text
- Cut: all but the most critical insights and arguments
- Preserve: only the most important concepts and takeaways
- Heavy paraphrasing to extreme brevity
- Transitions may be abrupt; focus on density of information

**Priority:** Maximum information density; flow and voice heavily compromised.
""",

    9: """
**Aggressiveness Level 9: Extreme (25-35% retention)**

Distill to absolute core concepts. Almost like a summary.

**Approach:**
- Extreme condensation, bordering on summarization
- Cut: everything except absolute core insights
- Preserve: only the most essential concepts and conclusions
- Complete paraphrasing for maximum brevity
- Flow and transitions minimal; focus purely on key information

**Priority:** Capture only the absolute essentials; natural flow abandoned.
""",

    10: """
**Aggressiveness Level 10: Maximum (10-20% retention)**

Extract only the absolute essential insights. Extremely condensed highlights.

**Approach:**
- Extreme summarization mode
- Cut: everything except the most critical insights that define the content
- Preserve: only insights that would be unacceptable to lose
- Maximum brevity through aggressive paraphrasing
- No concern for flow or natural speech; pure information extraction

**Priority:** Absolute minimum viable content; this is essentially a summary of key points.
"""
}

# ==============================================================================
# LEVEL 3: USER PROMPT - Transcript and target word count
# ==============================================================================

CONDENSE_USER_PROMPT = """
Condense the following transcript from {original_word_count} words down to approximately {target_word_count} words ({target_percentage:.0f}% of original length).

<transcript>
{transcript}
</transcript>
"""

def get_strategy_description(aggressiveness: int) -> str:
    """Get condensing strategy description based on aggressiveness level."""
    strategies = {
        1: "Conservative (70-80% retention): Remove only obvious 'filler' material. Keep almost all content intact.",
        2: "Light (65-75% retention): Remove filler and some repetitive statements. Preserve detailed examples.",
        3: "Gentle (60-70% retention): Remove filler, repetitions, and tangents. Keep most examples.",
        4: "Moderate-Light (55-65% retention): Remove filler, repetitions, tangents, and less important examples.",
        5: "Moderate (45-55% retention): Remove all filler, repetitions, tangents, and keep only key examples. Standard condensation.",
        6: "Moderate-Aggressive (40-50% retention): Keep only core insights and essential examples. Remove most elaborations.",
        7: "Aggressive (35-45% retention): Focus on main arguments and key insights. Minimal examples, only if critical.",
        8: "Very Aggressive (30-40% retention): Extract only the most important insights. Very minimal context.",
        9: "Extreme (25-35% retention): Distill to absolute core concepts. Almost like a summary.",
        10: "Maximum (10-20% retention): Extract only the absolute essential insights. Extremely condensed highlights."
    }
    return strategies.get(aggressiveness, strategies[5])


def get_condense_prompt(
    transcript: str,
    duration_minutes: float,
    aggressiveness: int = 5,
    target_reduction_percentage: int = None
) -> tuple[str, str]:
    """
    Generate the condensing prompts (system and user) with all parameters filled in.

    Uses three-level prompt structure:
    1. General system instructions (CONDENSE_SYSTEM_PROMPT)
    2. Aggressiveness-specific strategy (STRATEGY_PROMPTS[aggressiveness])
    3. Transcript and target word count (CONDENSE_USER_PROMPT)

    Args:
        transcript: The full transcript text
        duration_minutes: Original video duration in minutes (not used in prompts, kept for compatibility)
        aggressiveness: Condensing aggressiveness (1-10)
        target_reduction_percentage: Optional specific reduction target

    Returns:
        Tuple of (system_prompt, user_prompt)
    """
    # Calculate word counts
    original_word_count = len(transcript.split())

    if target_reduction_percentage is None:
        # Get retention percentage from table
        retention_pct = TARGET_RETENTION.get(aggressiveness, 30)
        target_reduction_percentage = 100 - retention_pct

    # Calculate retention percentage (inverse of reduction)
    retention_percentage = 100 - target_reduction_percentage

    # Calculate target word count
    target_word_count = int(original_word_count * (retention_percentage / 100))

    # Build system prompt: Level 1 (general) + Level 2 (strategy-specific)
    strategy_prompt = STRATEGY_PROMPTS.get(aggressiveness, STRATEGY_PROMPTS[5])
    system_prompt = CONDENSE_SYSTEM_PROMPT.strip() + "\n\n" + strategy_prompt.strip()

    # Build user prompt: Level 3 (transcript + word count)
    user_prompt = CONDENSE_USER_PROMPT.format(
        original_word_count=original_word_count,
        target_word_count=target_word_count,
        target_percentage=retention_percentage,
        transcript=transcript
    )

    return system_prompt, user_prompt


# Additional prompts for future features

# EXTRACT_KEY_POINTS_PROMPT = """Analyze this transcript and extract the key points, insights, and takeaways.

# Transcript:
# {transcript}

# Provide a structured list of:
# 1. Main topics discussed
# 2. Key insights and arguments
# 3. Important examples or case studies
# 4. Actionable takeaways
# 5. Conclusions

# Format as JSON."""


# IDENTIFY_GRAPHICS_MOMENTS_PROMPT = """Analyze this condensed script and identify where graphics, slides, or visual aids would be most valuable.

# Script:
# {script}

# For each suggested graphics moment, provide:
# - Timestamp estimate
# - Type of graphic (chart, diagram, text overlay, etc.)
# - Content description
# - Purpose (clarify, emphasize, illustrate)

# Format as JSON array."""
