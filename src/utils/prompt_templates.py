"""LLM prompt templates for content condensing.

Three-level prompt structure:
1. SYSTEM_PROMPT: General instructions, not specific to video or aggressiveness
2. STRATEGY_PROMPTS: Level-specific instructions (one for each aggressiveness 1-10)
3. USER_PROMPT: Contains the transcript and target word count
"""
import logging

logger = logging.getLogger(__name__)

# ==============================================================================
# TARGET RETENTION PERCENTAGES - Single source of truth
# ==============================================================================

# true geometric progression 10=75"
# 10.0, 12.5, 15.6, 19.6, 24.5, 30.6, 38.3, 47.9, 60.0, 75.0
# Target retention percentages (geometric progression from 75 to 10)
TARGET_RETENTION = {
    1: 75,   # 25% reduction, range 70-80%
    2: 60,   # 40% reduction, range 55-65%
    3: 50,   # 50% reduction, range 45-55%
    4: 38,   # 62% reduction, range 35-45%
    5: 30,   # 70% reduction, range 25-35%
    6: 25,   # 75% reduction, range 20-30%
    7: 20,   # 80% reduction, range 15-25%
    8: 16,   # 84% reduction, range 10-20%
    9: 13,   # 87% reduction, range 8-18%
    10: 10,  # 90% reduction, range 5-15%
}

# Human-readable retention ranges per aggressiveness level
RETENTION_RANGES = {
    1:  "70-80%",
    2:  "55-65%",
    3:  "45-55%",
    4:  "35-45%",
    5:  "25-35%",
    6:  "20-30%",
    7:  "15-25%",
    8:  "10-20%",
    9:  "8-18%",
    10: "5-15%",
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

At higher aggressiveness levels you will in fact have to summarize, rather than just edit.
Even at medium aggressveness levels you will have to restructure sentences.
When you do, bear in mind that the output is meant to be **spoken** (by TTS) and listened to, not read.
Thus, even when the original speaker's "voice" must be sacrificed, the output should still sound natural 
when spoken. To this end, prefer short sentences; favor contrast. Write for listening, not reading.

E.g. 
 - *Poor*: 
   This system improves efficiency by reducing latency and optimizing throughput across services.
 - *Better*:
   This system does one thing well.
   It makes everything faster.

Express numbers with units with the fully spelled out unit name, e.g.

**BAD**: 4.5 MB
**GOOD**: 4.5 megabytes
**BAD**: 100 ms
**GOOD**: 100 milliseconds

Write out numbers in words, not numerals, e.g.

**BAD**: About 307,000 lines across roughly 1,600 source files
**GOOD**: About three hundred seven thousand lines across roughly one thousand six hundred source files

The newlines are meaningful to the TTS engine. Use them judiciously to improve the prosody of the output.

**What can always be CUT:**
- ALWAYS cut entirely any promotional material, sponsorship mentions, and calls to action
- Tangents, personal anecdotes that don't support the main points
  (e.g., how this recipe came to be; the history of science from Aristotle to the discovery at hand;
  the speaker's personal journey to discovering the topic)
- Redundant examples that illustrate the same concept multiple times
- Supporting details that are interesting but not essential to the core insights
- If the transcript begins with a "highlights reel", this should be cut, as you will be providing
  your own "key points preserved" in the output

**What should be PRESERVED:**
- Unique key insights and main arguments
- Essential context needed to understand the above
- Logical transitions between topics
- Critical examples that clarify complex concepts
- Conclusions and takeaways
- The speaker's voice, personality, and speaking style at less aggressive levels.
  Don't substitute less technical or less formal terminology if the speaker uses such

**Constraints:**
1. As previously stated, the condensed script should sound natural when spoken aloud
2. Maintain coherent narrative flow with smooth transitions
3. Preserve the speaker's voice, personality, and speaking style even when paraphrasing
   (not relevant when **summarizing** at higher aggressiveness levels)
4. Keep the content engaging and easy to follow

**Important: Hit the target word count**
Do not try to adapt your condensation *aggressiveness* to the information density of the source content.
Instead, honor the user's target word counts, and do your best to preserve the most important insights 
near the target word count constraint. This may mean losing more key insights than you would personally
choose to lose, or leaving in some fluff that could well have been cut.

**Output Instructions:**

Output must be valid JSON and must conform to the JSON Schema provided by the API.

Remember to format the condensed_script with paragraph breaks (\n\n) at natural transitions.
"""

# ==============================================================================
# LEVEL 2: STRATEGY PROMPTS - Aggressiveness-specific instructions (1-10)
# ==============================================================================

STRATEGY_PROMPTS = {
    1: """
        **Aggressiveness Level 1/10: Conservative ({retention_range} retention)**

        The following instructions are additive of the general system instructions, and are specific
        to this particular aggressiveness level.

        **Approach:**
        - Think like editing a movie: you can cut scenes or dialogue, but normally you don't change what the actors say
        - Retain some entire passages from the original transcript verbatim when it is not excesively verbose
        - Paraphrase sparingly to achieve word count
        - Phrases and entire sentences may be cut if they do not contribute to the key insights

        **Priority:** Preserve the speaker's voice and natural flow.
    """,

    2: """
        **Aggressiveness Level 2/10: Light ({retention_range} retention)**

        The following instructions are additive of the general system instructions, and are specific
        to this particular aggressiveness level.

        **Approach:**
        - Light paraphrasing and strategic cuts

        **Priority:** Minimal loss of content, preserving the speaker's voice and natural flow.
    """,

    3: """
        **Aggressiveness Level 3/10: Gentle ({retention_range} retention)**

        The following instructions are additive of the general system instructions, and are specific
        to this particular aggressiveness level.

        **Approach:**
        - Verbatim retention only for sentences or phrases that are impactful or uniquely expressed
        - Paraphrase more freely to tighten content and reduce word count
        - Some cutting is inevitable at this aggressiveness level

        **Priority:** Clean up the content while keeping the speaker's voice recognizable.
    """,

    4: """
        **Aggressiveness Level 4/10: Moderate-Light ({retention_range} retention)**

        The following instructions are additive of the general system instructions, and are specific
        to this particular aggressiveness level.

        **Approach:**
        - Verbatim retention only for sentences or phrases that are impactful or uniquely expressed
        - Paraphrase more freely to tighten content and reduce word count
        - Some cutting is inevitable at this aggressiveness level

        **Priority:** Clean up the content while keeping the speaker's voice recognizable.
    """,

    5: """
        **Aggressiveness Level 5/10: Moderate ({retention_range} retention)**

        The following instructions are additive of the general system instructions, and are specific
        to this particular aggressiveness level.

        **Approach:**
        - Verbatim retention only for sentences or phrases that are impactful or uniquely expressed
        - Paraphrase very freely to tighten content and reduce word count
        - Cut freely but maintain logical flow and coherence

        **Priority:** Clean up the content while keeping the speaker's voice recognizable.
    """,

    6: """
        **Aggressiveness Level 6/10: Moderate-Aggressive ({retention_range} retention)**

        The following instructions are additive of the general system instructions, and are specific
        to this particular aggressiveness level.

        **Approach:**
        - Verbatim retention only for sentences or phrases that are impactful or uniquely expressed
        - Paraphrase very freely to tighten content and reduce word count
        - Cut freely but maintain logical flow and coherence

        **Priority:** Extract core content; speaker's voice becomes secondary to insights.
    """,

    7: """
        **Aggressiveness Level 7/10: Aggressive ({retention_range} retention)**

        The following instructions are additive of the general system instructions, and are specific
        to this particular aggressiveness level.

        **Approach:**
        - Verbatim retention only for sentences or phrases that are impactful or uniquely expressed
        - Paraphrase very freely to tighten content and reduce word count
        - Cut freely but maintain logical flow and coherence
        - Not all arguments or insights must be preserved at this level; focus on the most important ones

        **Priority:** Distill to main arguments and insights; natural flow still needed, but speaker's voice 
        is less of a concern.
    """,

    8: """
        **Aggressiveness Level 8/10: Very Aggressive ({retention_range} retention)**

        The following instructions are additive of the general system instructions, and are specific
        to this particular aggressiveness level.

        **Approach:**
        - Verbatim retention only for sentences or phrases that are impactful or uniquely expressed
        - Paraphrase very freely to tighten content and reduce word count
        - In some case go beyond paraphrasing; summarize
        - Cut freely but maintain logical flow and coherence
        - Not all arguments or insights must be preserved at this level; focus on the most important ones

        **Priority:** High information density
    """,

    9: """
        **Aggressiveness Level 9/10: Extreme ({retention_range} retention)**

        The following instructions are additive of the general system instructions, and are specific
        to this particular aggressiveness level.

        **Approach:**
        - Verbatim retention is not desired
        - Summarize, not just paraphrase
        - Cut freely but maintain logical flow and coherence
        - Not all arguments or insights must be preserved at this level; focus on the most important ones

        **Priority:** High information density
    """,

    10: """
        **Aggressiveness Level 10/10: Maximum ({retention_range} retention)**

        The following instructions are additive of the general system instructions, and are specific
        to this particular aggressiveness level.

        **Approach:**
        - Cut ruthlessly
        - Summarize
        - Maximum one or two key insights preserved; minimal supporting context
        - Speaker's voice is not a concern
        - Natural flow desired to the extent possible but may be compromised if necessary to hit word count

        **Priority:**  Maximum information density.
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

Respond with JSON per the system prompt instructions.
"""

TTS_SSML_REWRITE_INSTRUCTIONS = """
Now rewrite the previously generated condensed script for TTS.
Requirements:

- Optimize for listening, not reading
- Use short sentences and conversational phrasing
- Insert SSML tags supported by Azure Speech TTS
- Use <p> and <s> structure
- Add pauses with <break> where emphasis or pacing helps
- Use <emphasis> sparingly, only on contrast words
- Do not overuse prosody changes
- Do not add new content
- Output valid SSML only
- Output must be a single SSML document wrapped in <speak>...</speak>.
- Do not include a <voice> tag or any voice name/voice ID. Voice selection is handled separately.

Express numbers with units with the fully spelled out unit name, e.g.

**BAD**: 4.5 MB
**GOOD**: 4.5 megabytes
**BAD**: 100 ms
**GOOD**: 100 milliseconds

Write out numbers in words, not numerals, e.g.

**BAD**: About 307,000 lines across roughly 1,600 source files
**GOOD**: About three hundred seven thousand lines across roughly one thousand six hundred source files

"""

EXTRACT_TAKEAWAYS_PROMPT_BASE = """
You are analyzing a video transcript to extract the most important key concepts.

Extract exactly {N} key takeaways from this video. For each takeaway:
- Focus on the core concept or insight
- Explain it in 1-2 complete, self-contained sentences
- Make it actionable or memorable
- Ensure it can be understood without watching the video

Requirements:
- Exactly {N} takeaways, no more, no less
- Each must be substantive and distinct
- Order by importance (most important first)
- Use clear, concise language
- Each point should be 1-2 sentences maximum
"""

EXTRACT_TAKEAWAYS_AUTO_PROMPT_BASE = """
You are analyzing a video transcript to extract the most important key concepts.

First, analyze the content to determine the optimal number of key takeaways (between 3-10).
Consider:
- Video length and content density
- Complexity of topics covered
- Natural information hierarchy
- Avoiding redundancy while capturing all major concepts
- Fewer is better

Then extract that optimal number of key takeaways. For each:
- Focus on the core concept or insight
- Explain in 1 sentence.
- Make it actionable or memorable

Order by importance (most important first).
"""

TAKEAWAYS_FORMAT_MARKDOWN = """
Output as a numbered markdown list:
1. **[Key concept]** — [Explanation in 1-2 sentences]
2. **[Key concept]** — [Explanation in 1-2 sentences]
...
[Continue until all key concepts are covered]

Do not introduce the list with any heading or title.
"""

TAKEAWAYS_FORMAT_PLAIN_TEXT = """
Output as a simple numbered list (no markdown formatting):
1. [Key concept] - [Explanation in 1-2 sentences]
2. [Key concept] - [Explanation in 1-2 sentences]
...
[Continue until all key concepts are covered]

Do not introduce the list with any heading or title; just the list items. 
Do not use any markdown formatting.
Dashes and em-dashes are permitted. The text will be fed to TTS, so these can be helpful for pacing.
"""

def get_strategy_description(aggressiveness: int) -> str:
    """Get condensing strategy description based on aggressiveness level."""
    retention_range = RETENTION_RANGES.get(aggressiveness, RETENTION_RANGES[5])
    strategies = {
        1:  f"Conservative ({retention_range} retention)",
        2:  f"Light ({retention_range} retention)",
        3:  f"Gentle ({retention_range} retention)",
        4:  f"Moderate-Light ({retention_range} retention)",
        5:  f"Moderate ({retention_range} retention)",
        6:  f"Moderate-Aggressive ({retention_range} retention)",
        7:  f"Aggressive ({retention_range} retention)",
        8:  f"Very Aggressive ({retention_range} retention)",
        9:  f"Extreme ({retention_range} retention)",
        10: f"Maximum ({retention_range} retention)",
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
    retention_range = RETENTION_RANGES.get(aggressiveness, RETENTION_RANGES[5])
    strategy_prompt = STRATEGY_PROMPTS.get(aggressiveness, STRATEGY_PROMPTS[5]).format(retention_range=retention_range)

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
