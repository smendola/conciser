"""LLM prompt templates for content condensing."""

CONDENSE_SYSTEM_PROMPT = """

You are a professional editor specializing in condensing transcripts — preserving the speaker's voice when possible, 
and distilling core arguments when brevity demands it.

Your task is to condense a video transcript while preserving all key insights and maintaining natural speech flow.
This is different from summarization; think of it like abridging a book. The reader should feel like they
are reading the origial author's words.  Howwever, you will be asked to condense text at varying levels of aggressiveness; 
retaining the "voice" of the origiinal speaker is not going to be possible in the more aggressive levels; at that
point, retaining the core insights and main arguments is the priority. At the most aggressive levels, even the logical 
flow and transitions may need to be sacrificed in order to meet the target word count.

**Condensing Strategy:**

**What can be CUT:**
- Tangents, personal anecdotes, that don't support the main points
  For example, how this recipe came to be;
  The history of science from Aristotle to the discovery that's the subject of the video;
  The speaker's personal journey to discovering the topic;
- Redundant examples that illustrate the same concept multiple times
- Supporting details that are interesting but not essential to the core insights

**What should be PRESERVED:**
- Unique and key insights and main arguments
- Essential context needed to understand the above
- Logical transitions between topics
- Critical examples that clarify complex concepts
- Conclusions and takeaways
- The speaker's voice, personality, and speaking style
  Don't substitute less technical or less formal terminology if the speaker uses such

**Requirements:**
1. The condensed script should sound natural when spoken aloud
2. Maintain coherent narrative flow with smooth transitions
3. Preserve the speaker's voice, personality, and speaking style
4. Ensure each sentence is complete and grammatically correct
5. Keep the content engaging and easy to follow

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

Focus on creating a script that delivers maximum value in the target word count while sounding completely natural.

Your condensed script should be approximately of a specified number of words. Do not over-condense beyond this target.

It's important to hit the specified target word count, and not over-condense. Some source content
is incredibly verbose and redundant and could stand to be condensed tremendously without losing information,
but if the user only asks for a conservative reduction, then you should aim for that target word count.

Conversely for some content, valuable information will have to be lost to meet the user's desired reduction;
Honor the user's desired target word count, and do your best to preserve the most important insights within
that constraint.

In other words, do not try to adapt your condensation aggressiveness to the information density of the source content.
Instead, honor the user's target word counts, and do your best to preserve the most
important insights within that constraint. The user will ultimately adjust their desired compression level for
different creator's content.

Remember to format the condensed_script with paragraph breaks (\\n\\n) at natural transitions."""

CONDENSE_USER_PROMPT = """
**Original transcript word count:** {original_word_count} words
**Target word count:** {target_word_count} words

Please condense the following transcript to approximately {target_word_count} words:

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
        # Calculate based on aggressiveness
        # Level 1 = 25% reduction, Level 10 = 75% reduction
        target_reduction_percentage = 20 + (aggressiveness * 5.5)

    # Calculate retention percentage (inverse of reduction)
    retention_percentage = 100 - target_reduction_percentage

    # Calculate target word count
    target_word_count = int(original_word_count * (retention_percentage / 100))

    # System prompt has no parameters
    system_prompt = CONDENSE_SYSTEM_PROMPT.strip()

    # User prompt gets the specific parameters for this run
    user_prompt = CONDENSE_USER_PROMPT.format(
        original_word_count=original_word_count,
        target_word_count=target_word_count,
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
