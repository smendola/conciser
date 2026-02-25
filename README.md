# NBJ Condenser - AI-Powered Video Condensation

NBJ Condenser is an intelligent video condensation tool that automatically shortens videos by removing filler content while preserving key insights. It uses AI voice cloning and video generation to create a natural, condensed version with the original speaker's voice and appearance.

## Features

- **Intelligent Content Analysis**: Uses Claude AI to identify and remove filler, repetitions, and tangents
- **Voice Cloning**: Clones the original speaker's voice using ElevenLabs
- **Video Regeneration**: Creates lip-synced talking head video using D-ID
- **Adjustable Aggressiveness**: Control how much content to remove (1-10 scale)
- **High Quality Output**: Supports 720p, 1080p, and 4K output
- **Automatic Watermarking**: Adds AI-generated content watermark

## How It Works

NBJ Condenser processes videos through a 7-stage pipeline:

1. **Download**: Downloads video from YouTube or other sources
2. **Transcribe**: Converts speech to text using OpenAI Whisper
3. **Condense**: AI analyzes and condenses the transcript
4. **Voice Clone**: Clones the speaker's voice from the original audio
5. **Speech Generation**: Creates new audio with the condensed script
6. **Video Generation**: Generates lip-synced talking head video
7. **Final Assembly**: Combines everything into the final output

## Installation

### Prerequisites

- Python 3.10 or higher
- ffmpeg and ffprobe (for audio/video processing)
- API keys from:
  - [OpenAI](https://platform.openai.com/api-keys) (for Whisper)
  - [Anthropic](https://console.anthropic.com/) (for Claude)
  - [ElevenLabs](https://elevenlabs.io/) (for voice cloning)
  - [D-ID](https://www.d-id.com/) (for video generation)

### Install ffmpeg

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install ffmpeg
```

**macOS:**
```bash
brew install ffmpeg
```

**Windows:**
Download from [ffmpeg.org](https://ffmpeg.org/download.html)

### Install NBJ Condenser

```bash
# Clone the repository
git clone https://github.com/yourusername/nbj.git
cd nbj

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install in development mode
pip install -e .
```

## Configuration

### Quick Setup

Run the interactive setup wizard:

```bash
nbj setup
```

This will prompt you for your API keys and create a `.env` file.

### Manual Setup

Copy the example environment file and fill in your API keys:

```bash
cp .env.example .env
```

Edit `.env` and add your API keys:

```env
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
ELEVENLABS_API_KEY=...
DID_API_KEY=...
```

### Verify Configuration

Check that everything is configured correctly:

```bash
nbj check
```

## Usage

### Basic Usage

Condense a video with default settings (50% reduction):

```bash
nbj condense https://youtube.com/watch?v=VIDEO_ID
```

### Adjust Aggressiveness

Control how much content to remove (1-10 scale):

```bash
# Conservative (remove ~25% - mostly filler)
nbj condense https://youtube.com/watch?v=VIDEO_ID -a 1

# Moderate (remove ~50% - filler + tangents)
nbj condense https://youtube.com/watch?v=VIDEO_ID -a 5

# Aggressive (remove ~75% - keep only key insights)
nbj condense https://youtube.com/watch?v=VIDEO_ID -a 10
```

### Specify Output Quality

```bash
nbj condense https://youtube.com/watch?v=VIDEO_ID -q 720p
nbj condense https://youtube.com/watch?v=VIDEO_ID -q 1080p
nbj condense https://youtube.com/watch?v=VIDEO_ID -q 4k
```

### Custom Output Path

```bash
nbj condense https://youtube.com/watch?v=VIDEO_ID -o ./my_video.mp4
```

### Target Specific Reduction

Override aggressiveness with exact reduction percentage:

```bash
nbj condense https://youtube.com/watch?v=VIDEO_ID --reduction 60
```

### Get Video Info

Preview information before processing:

```bash
nbj info https://youtube.com/watch?v=VIDEO_ID
```

## Aggressiveness Levels Guide

| Level | Reduction | What's Removed | Best For |
|-------|-----------|----------------|----------|
| 1-2 | 20-30% | Filler words, long pauses | Light cleanup |
| 3-4 | 35-45% | Filler, some repetitions | Gentle condensing |
| 5-6 | 50-60% | Filler, repetitions, tangents | Standard use |
| 7-8 | 65-75% | All above + detailed examples | Aggressive condensing |
| 9-10 | 75-85% | Everything except core insights | Maximum condensing |

## Cost Estimates

Typical costs for a 30-minute podcast → 10-minute condensed version:

- **Transcription** (Whisper): ~$0.18
- **Condensing** (Claude): ~$3-5
- **Voice Cloning** (ElevenLabs): ~$2
- **Video Generation** (D-ID): ~$3-5

**Total: $8-12 per video**

Costs scale roughly linearly with video length.

## Examples

### Educational Content

```bash
# Condense a 1-hour lecture to 20 minutes
nbj condense https://youtube.com/watch?v=LECTURE_ID -a 7
```

### Podcast Interview

```bash
# Condense a 2-hour podcast to 40 minutes
nbj condense https://youtube.com/watch?v=PODCAST_ID -a 6
```

### Tutorial Video

```bash
# Light condensing, keep most content
nbj condense https://youtube.com/watch?v=TUTORIAL_ID -a 3
```

## Output Structure

NBJ Condenser creates the following directories:

```
nbj/
├── output/          # Final condensed videos
├── temp/            # Temporary processing files
└── nbj.log     # Processing log
```

## Troubleshooting

### "API key not set" error

Run `nbj setup` or manually add keys to `.env` file.

### "ffmpeg not found" error

Install ffmpeg using your package manager (see Installation section).

### Video generation takes too long

This is normal. Video generation can take 2-5 minutes per minute of output video. For a 10-minute video, expect 20-50 minutes processing time.

### Voice quality is poor

The quality depends on the source audio. Ensure:
- Original video has clear audio
- Minimal background noise
- Speaker is the primary audio source

### Out of credits errors

Check your API credits:
- OpenAI: https://platform.openai.com/account/usage
- Anthropic: https://console.anthropic.com/
- ElevenLabs: https://elevenlabs.io/
- D-ID: https://studio.d-id.com/

## Advanced Usage

### Resume Failed Jobs

If a job fails mid-process, you can resume by examining the temp directory and calling individual pipeline stages. Full resume support coming in a future update.

### Batch Processing

Process multiple videos by running nbj in a loop:

```bash
for url in $(cat video_urls.txt); do
  nbj condense "$url" -a 5
done
```

## Limitations

- **Phase 1 only**: Currently only processes talking head videos. Graphics/B-roll preservation coming in Phase 2.
- **Single speaker**: Multi-speaker support coming in Phase 3.
- **English only**: Best results with English content (Whisper supports other languages but quality varies).
- **API dependent**: Requires internet connection and API credits.

## Roadmap

### Phase 2: Graphics & Visual Enhancement
- Automatic graphics detection
- B-roll preservation
- Intelligent re-insertion of visual elements

### Phase 3: Advanced Features
- Web UI
- Multi-speaker support
- Batch processing
- Custom voice/face selection
- Resume capability
- Preview mode

## Legal & Ethical Considerations

- **Copyright**: Ensure you have rights to process the videos. NBJ Condenser is intended for fair use transformation.
- **Attribution**: Generated videos are watermarked as AI-generated.
- **Accuracy**: AI condensation may miss context. Always review output before sharing.
- **Deepfake concerns**: Use responsibly. Do not create misleading content.

## Contributing

Contributions welcome! Please open an issue or PR.

## License

MIT License - see LICENSE file for details.

## Support

- **Issues**: https://github.com/yourusername/nbj/issues
- **Discussions**: https://github.com/yourusername/nbj/discussions

## Credits

Built with:
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) - Video downloading
- [OpenAI Whisper](https://openai.com/research/whisper) - Transcription
- [Anthropic Claude](https://www.anthropic.com/) - Content analysis
- [ElevenLabs](https://elevenlabs.io/) - Voice cloning
- [D-ID](https://www.d-id.com/) - Video generation

## Disclaimer

This tool is for educational and research purposes. Users are responsible for compliance with applicable laws and terms of service. The authors are not liable for misuse.
