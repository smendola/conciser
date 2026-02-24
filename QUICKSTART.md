# Quick Start Guide

Get started with Conciser in 5 minutes!

## Prerequisites

Before you begin, make sure you have:

1. **Python 3.10+** installed
2. **ffmpeg** installed (required for video processing)
3. API keys from:
   - OpenAI: https://platform.openai.com/api-keys
   - Anthropic: https://console.anthropic.com/
   - ElevenLabs: https://elevenlabs.io/
   - D-ID: https://www.d-id.com/

## Installation

### 1. Install ffmpeg

**Ubuntu/Debian:**
```bash
sudo apt update && sudo apt install ffmpeg
```

**macOS:**
```bash
brew install ffmpeg
```

**Windows:**
Download from https://ffmpeg.org/download.html and add to PATH

### 2. Install Conciser

```bash
# Clone or download the repository
cd conciser

# Create virtual environment
python -m venv venv

# Activate virtual environment
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install Conciser
pip install -e .
```

### 3. Configure API Keys

Run the setup wizard:

```bash
conciser setup
```

Or manually create a `.env` file:

```bash
cp .env.example .env
```

Then edit `.env` and add your API keys.

### 4. Verify Installation

```bash
conciser check
```

You should see all checks pass.

## Your First Condensed Video

### Step 1: Find a Video

Choose a YouTube video to condense. Good candidates:
- Podcasts with lots of filler
- Long educational lectures
- Interview videos
- Talking head videos (no complex graphics yet)

### Step 2: Get Video Info (Optional)

Check the video details and estimated cost:

```bash
conciser info "https://youtube.com/watch?v=VIDEO_ID"
```

### Step 3: Condense the Video

Start with moderate aggressiveness (level 5):

```bash
conciser condense "https://youtube.com/watch?v=VIDEO_ID" -a 5
```

This will:
1. Download the video (~30 seconds)
2. Transcribe audio (~1-2 minutes)
3. Condense with AI (~2-3 minutes)
4. Clone voice (~1-2 minutes)
5. Generate speech (~2-5 minutes)
6. Generate video (~20-50 minutes for a 10-min output)
7. Compose final video (~1 minute)

**Total time: ~30-60 minutes for a 30-minute source video**

### Step 4: Review Output

Your condensed video will be in the `output/` directory:

```
output/
└── Your_Video_Title_condensed.mp4
```

## Understanding Aggressiveness Levels

Try different levels to see what works best:

```bash
# Light condensing - remove ~30%
conciser condense "URL" -a 3

# Moderate - remove ~50% (recommended)
conciser condense "URL" -a 5

# Aggressive - remove ~70%
conciser condense "URL" -a 8
```

## Common Options

### Choose Output Quality

```bash
# 720p (faster, smaller file)
conciser condense "URL" -a 5 -q 720p

# 1080p (default, balanced)
conciser condense "URL" -a 5 -q 1080p

# 4K (slower, larger file)
conciser condense "URL" -a 5 -q 4k
```

### Custom Output Location

```bash
conciser condense "URL" -a 5 -o ./my_videos/condensed.mp4
```

### Exact Reduction Target

```bash
# Remove exactly 60% of content
conciser condense "URL" --reduction 60
```

## Tips for Best Results

### 1. Choose Good Source Videos
- Clear audio with minimal background noise
- Single speaker (multi-speaker coming in Phase 2)
- Mostly talking head (graphics preservation coming in Phase 2)
- English language (best support)

### 2. Start Conservative
- Try aggressiveness 3-4 first
- Increase if you want more condensing
- Very high levels (9-10) may lose important context

### 3. Monitor Costs
- Check API usage after first video
- Typical cost: $8-12 per 30-minute video
- Set up billing alerts in your API dashboards

### 4. Review Output
- Always watch the condensed video before sharing
- AI may occasionally miss context or create artifacts
- Lip sync quality varies based on source material

## Troubleshooting

### Error: "API key not set"
Run `conciser setup` or check your `.env` file.

### Error: "ffmpeg not found"
Install ffmpeg (see installation section above).

### Video generation is very slow
This is normal. D-ID processes video in real-time or slower. A 10-minute output takes 20-50 minutes.

### Voice doesn't sound like original
Try using a longer source video (30+ minutes) for better voice cloning samples.

### Out of credits
Check your API dashboards and add credits:
- OpenAI: https://platform.openai.com/account/billing
- Anthropic: https://console.anthropic.com/settings/billing
- ElevenLabs: https://elevenlabs.io/subscription
- D-ID: https://studio.d-id.com/billing

## Example Workflows

### Condense a Podcast
```bash
# 2-hour podcast → 40-minute highlights
conciser condense "https://youtube.com/watch?v=PODCAST_ID" -a 6 -q 1080p
```

### Condense a Lecture
```bash
# 1-hour lecture → 20-minute summary
conciser condense "https://youtube.com/watch?v=LECTURE_ID" -a 7 -q 720p
```

### Light Cleanup
```bash
# 30-minute video → 22-minute cleaned version
conciser condense "https://youtube.com/watch?v=VIDEO_ID" -a 2 -q 1080p
```

## Next Steps

- Read the full [README.md](README.md) for detailed documentation
- Check [examples/](examples/) for sample outputs
- Join our community to share results and get help
- Star the repo if you find it useful!

## Getting Help

- **Check the log**: `conciser.log` has detailed error messages
- **Run diagnostics**: `conciser check` to verify setup
- **Read documentation**: [README.md](README.md)
- **Report issues**: GitHub Issues

## Cost Management

### Estimated Costs (per video)

30-minute video → 10-minute condensed:
- Whisper: $0.18
- Claude: $3-5
- ElevenLabs: $2
- D-ID: $3-5
- **Total: ~$8-12**

### Ways to Reduce Costs

1. **Use lower quality**: `-q 720p` uses fewer D-ID credits
2. **Conservative aggressiveness**: Less condensing = shorter output = lower cost
3. **Batch processing**: Process multiple videos when you have time
4. **Monitor usage**: Check API dashboards regularly

## What's Next?

You've successfully set up and run Conciser! Here are some ideas:

1. Try different aggressiveness levels to find your sweet spot
2. Experiment with different types of content
3. Compare output quality at different resolutions
4. Set up batch processing for multiple videos
5. Contribute improvements or report issues on GitHub

Happy condensing! 🎬✨
