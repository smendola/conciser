"""LLM prompt templates for content condensing."""

CONDENSE_TRANSCRIPT_PROMPT = """You are an expert video editor specializing in content condensation. Your task is to condense a video transcript while preserving all key insights and maintaining natural speech flow.

**Original Video Information:**
- Duration: {duration_minutes} minutes
- Target reduction: {reduction_percentage}% (aim for ~{target_duration_minutes} minutes)
- Aggressiveness level: {aggressiveness}/10

**Condensing Strategy:**

For aggressiveness {aggressiveness}/10:
{strategy_description}

**What to REMOVE:**
- Filler words (um, uh, like, you know, etc.)
- Long pauses and dead air
- Repetitive statements that don't add new information
- Tangents that don't support the main points
- Overly detailed examples (keep only the most illustrative ones)
- Redundant explanations

**What to PRESERVE:**
- All unique key insights and main arguments
- Essential context needed to understand the points
- The speaker's personality and tone
- Logical transitions between topics
- Critical examples that clarify complex concepts
- Conclusions and takeaways

**Requirements:**
1. The condensed script MUST sound natural when spoken aloud
2. Maintain coherent narrative flow with smooth transitions
3. Preserve the speaker's voice, personality, and speaking style
4. Ensure each sentence is complete and grammatically correct
5. Keep the content engaging and easy to follow

**Original Transcript:**
{transcript}

**Output Instructions:**
Generate a JSON response with the following structure:
{{
  "condensed_script": "The full condensed script formatted naturally for speech. IMPORTANT: Format the script with paragraph breaks (using \\n\\n) at natural topic transitions and logical breaks. Each paragraph should cover a cohesive idea or topic. This makes the script easier to read and more natural when spoken.",
  "original_duration_minutes": {duration_minutes},
  "estimated_condensed_duration_minutes": <your estimate>,
  "reduction_percentage": <actual reduction percentage achieved>,
  "key_points_preserved": [
    "First key point or insight preserved",
    "Second key point or insight preserved",
    "Third key point or insight preserved"
  ],
  "removed_content_summary": "Brief description of what types of content were removed",
  "quality_notes": "Any notes about the condensation quality or challenges encountered"
}}

Focus on creating a script that delivers maximum value in minimum time while sounding completely natural. Remember to format the condensed_script with paragraph breaks (\\n\\n) at natural transitions."""


def get_strategy_description(aggressiveness: int) -> str:
    """Get condensing strategy description based on aggressiveness level."""
    strategies = {
        1: "Conservative (70-80% retention): Remove only obvious filler words and long pauses. Keep almost all content intact.",
        2: "Light (65-75% retention): Remove filler and some repetitive statements. Preserve detailed examples.",
        3: "Gentle (60-70% retention): Remove filler, repetitions, and minor tangents. Keep most examples.",
        4: "Moderate-Light (55-65% retention): Remove filler, repetitions, tangents, and less important examples.",
        5: "Moderate (45-55% retention): Remove all filler, repetitions, tangents, and keep only key examples. Standard condensation.",
        6: "Moderate-Aggressive (40-50% retention): Keep only core insights and essential examples. Remove most elaborations.",
        7: "Aggressive (35-45% retention): Focus on main arguments and key insights. Minimal examples, only if critical.",
        8: "Very Aggressive (30-40% retention): Extract only the most important insights. Very minimal context.",
        9: "Extreme (25-35% retention): Distill to absolute core concepts. Almost like a summary.",
        10: "Maximum (20-30% retention): Extract only the absolute essential insights. Extremely condensed highlights."
    }
    return strategies.get(aggressiveness, strategies[5])


def get_condense_prompt(
    transcript: str,
    duration_minutes: float,
    aggressiveness: int = 5,
    target_reduction_percentage: int = None
) -> str:
    """
    Generate the condensing prompt with all parameters filled in.

    Args:
        transcript: The full transcript text
        duration_minutes: Original video duration in minutes
        aggressiveness: Condensing aggressiveness (1-10)
        target_reduction_percentage: Optional specific reduction target

    Returns:
        Formatted prompt string
    """
    if target_reduction_percentage is None:
        # Calculate based on aggressiveness
        # Level 1 = 25% reduction, Level 10 = 75% reduction
        target_reduction_percentage = 20 + (aggressiveness * 5.5)

    target_duration_minutes = duration_minutes * (1 - target_reduction_percentage / 100)

    return CONDENSE_TRANSCRIPT_PROMPT.format(
        duration_minutes=round(duration_minutes, 1),
        target_duration_minutes=round(target_duration_minutes, 1),
        reduction_percentage=int(target_reduction_percentage),
        aggressiveness=aggressiveness,
        strategy_description=get_strategy_description(aggressiveness),
        transcript=transcript
    )


# Additional prompts for future features

EXTRACT_KEY_POINTS_PROMPT = """Analyze this transcript and extract the key points, insights, and takeaways.

Transcript:
{transcript}

Provide a structured list of:
1. Main topics discussed
2. Key insights and arguments
3. Important examples or case studies
4. Actionable takeaways
5. Conclusions

Format as JSON."""


IDENTIFY_GRAPHICS_MOMENTS_PROMPT = """Analyze this condensed script and identify where graphics, slides, or visual aids would be most valuable.

Script:
{script}

For each suggested graphics moment, provide:
- Timestamp estimate
- Type of graphic (chart, diagram, text overlay, etc.)
- Content description
- Purpose (clarify, emphasize, illustrate)

Format as JSON array."""
