# NBJ Condenser Architecture

This document provides a technical overview of NBJ Condenser's architecture and implementation details.

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        User Interface                        │
│                     (CLI - Click-based)                      │
└────────────────────────────┬────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────┐
│                    Pipeline Orchestrator                     │
│              (CondenserPipeline - src/pipeline.py)          │
└─┬──────┬──────┬──────┬──────┬──────┬──────────────────────┘
  │      │      │      │      │      │
  ▼      ▼      ▼      ▼      ▼      ▼
┌───┐  ┌───┐  ┌───┐  ┌───┐  ┌───┐  ┌───┐
│ 1 │  │ 2 │  │ 3 │  │ 4 │  │ 5 │  │ 6 │
└───┘  └───┘  └───┘  └───┘  └───┘  └───┘
 │      │      │      │      │      │
 │      │      │      │      │      │
 ▼      ▼      ▼      ▼      ▼      ▼
Download  Transcribe  Condense  Voice    Video   Compose
          Audio       Content   Clone    Generate
```

## Pipeline Stages

### Stage 1: Video Download
**Module**: `src/modules/downloader.py`

- Downloads video from YouTube using yt-dlp
- Extracts metadata (title, duration, uploader, etc.)
- Saves video in MP4 format
- Configurable quality (720p, 1080p, 4K)

**Key Components**:
- `VideoDownloader` class
- Format string generation for quality selection
- Metadata extraction

**External Dependencies**: yt-dlp, ffmpeg

### Stage 2: Audio Transcription
**Module**: `src/modules/transcriber.py`

- Extracts audio from video (WAV format, 16kHz)
- Sends audio to OpenAI Whisper API
- Receives timestamped transcript
- Identifies clean speech segments for voice cloning

**Key Components**:
- `Transcriber` class
- `extract_clean_speech_segments()` - Finds high-quality audio samples
- Transcript save/load functionality

**External Dependencies**: OpenAI API, ffmpeg

### Stage 3: Content Condensation
**Module**: `src/modules/condenser.py`

- Sends transcript + metadata to Claude API
- Uses sophisticated prompt engineering for quality condensing
- Receives condensed script with metadata
- Validates output structure

**Key Components**:
- `ContentCondenser` class
- Prompt templates (`src/utils/prompt_templates.py`)
- Strategy descriptions for each aggressiveness level
- JSON response parsing and validation

**External Dependencies**: Anthropic API

**Prompt Engineering Details**:
- Adaptive strategy based on aggressiveness (1-10)
- Preserves key insights while removing filler
- Maintains natural speech flow
- Returns structured JSON with metadata

### Stage 4: Voice Cloning
**Module**: `src/modules/voice_cloner.py`

- Extracts 2-5 minutes of clean speech samples
- Normalizes audio (volume leveling, noise reduction)
- Creates voice clone via ElevenLabs API
- Receives voice ID for speech generation

**Key Components**:
- `VoiceCloner` class
- Audio segment extraction
- Audio normalization
- Voice cleanup after processing

**External Dependencies**: ElevenLabs API, ffmpeg

**Audio Processing**:
- Multiple samples for better quality (up to 3 segments)
- Each segment: 30-60 seconds
- Normalization: loudnorm filter (-16 LUFS)

### Stage 5: Speech Generation
**Module**: `src/modules/voice_cloner.py` (continued)

- Generates speech from condensed script
- Uses cloned voice ID
- Handles long scripts via chunking
- Normalizes generated audio

**Key Components**:
- `generate_speech_chunked()` - Handles long text
- Sentence-aware chunking (5000 chars max)
- Audio concatenation for chunks

**External Dependencies**: ElevenLabs API, ffmpeg

### Stage 6: Video Generation
**Module**: `src/modules/video_generator.py`

- Extracts reference frame from original video
- Uploads image and audio to D-ID
- Polls for video generation completion
- Downloads generated talking head video

**Key Components**:
- `VideoGenerator` class (D-ID implementation)
- `HeyGenVideoGenerator` class (alternative, stub)
- File upload handling
- Polling with timeout

**External Dependencies**: D-ID API, requests

**Processing Details**:
- Reference frame extracted at 10s mark
- Lively animation driver for natural movement
- Stitch mode for better quality
- Timeout: 600s (10 minutes) default

### Stage 7: Final Composition
**Module**: `src/modules/compositor.py`

- Combines generated video with audio
- Adds AI-generated watermark
- Scales to target resolution
- Optimizes for streaming

**Key Components**:
- `VideoCompositor` class
- Watermark overlay
- Resolution scaling with padding
- Fast-start optimization

**External Dependencies**: ffmpeg

## Utility Modules

### Audio Utilities
**Module**: `src/utils/audio_utils.py`

Functions:
- `extract_audio()` - Extract audio from video
- `get_audio_duration()` - Get audio length
- `extract_audio_segment()` - Extract time range
- `normalize_audio()` - Volume normalization
- `get_video_resolution()` - Get video dimensions

### Video Utilities
**Module**: `src/utils/video_utils.py`

Functions:
- `combine_audio_video()` - Merge audio and video
- `extract_frame()` - Extract single frame as image
- `get_video_info()` - Get comprehensive metadata

### Prompt Templates
**Module**: `src/utils/prompt_templates.py`

- Condensation prompt template
- Strategy descriptions (1-10 aggressiveness)
- Dynamic prompt generation
- Future: Graphics placement prompts

## Configuration System

**Module**: `src/config.py`

Uses Pydantic Settings for type-safe configuration:
- Environment variable loading (.env)
- API key management
- Default values
- Directory creation
- Validation

**Configuration Sources**:
1. Environment variables
2. .env file
3. Default values in Settings class

## CLI Interface

**Module**: `src/main.py`

Built with Click framework:
- `nbj condense` - Main condensation command
- `nbj info` - Get video information
- `nbj setup` - Interactive setup wizard
- `nbj check` - Configuration diagnostics

**Features**:
- Colored output (colorama)
- Progress display
- Error handling
- Help documentation

## Data Flow

```
URL → Download → Video File → Audio Extraction → Audio File
                                                      ↓
                                                 Transcribe
                                                      ↓
                                                 Transcript
                                                      ↓
        ┌─────────────────────────────────────────────┴──────┐
        ↓                                                     ↓
   Voice Sample                                         Full Text
   Extraction                                                ↓
        ↓                                                  Condense
   Voice Clone                                               ↓
        ↓                                              Condensed Script
   Generate Speech ←────────────────────────────────────────┘
        ↓
   Generated Audio
        ↓
        ├──→ Reference Frame Extraction → Video Generation
        │                                       ↓
        └──→────────────────────────────→  Composition
                                                ↓
                                           Final Video
```

## File Structure

```
nbj/
├── src/
│   ├── __init__.py
│   ├── main.py                 # CLI entry point
│   ├── config.py               # Configuration management
│   ├── pipeline.py             # Main orchestrator
│   ├── modules/
│   │   ├── __init__.py
│   │   ├── downloader.py       # Stage 1: Download
│   │   ├── transcriber.py      # Stage 2: Transcribe
│   │   ├── condenser.py        # Stage 3: Condense
│   │   ├── voice_cloner.py     # Stage 4-5: Voice
│   │   ├── video_generator.py  # Stage 6: Video
│   │   └── compositor.py       # Stage 7: Compose
│   └── utils/
│       ├── audio_utils.py      # Audio processing
│       ├── video_utils.py      # Video processing
│       └── prompt_templates.py # LLM prompts
├── tests/
│   ├── __init__.py
│   └── test_pipeline.py
├── scripts/
│   ├── install.sh
│   └── test_setup.sh
├── requirements.txt
├── setup.py
├── .env.example
├── .gitignore
└── README.md
```

## Error Handling

### Strategy
- Fail fast with descriptive errors
- Log all operations to `nbj.log`
- User-friendly error messages in CLI
- Detailed technical errors in logs

### Error Types
- **Configuration errors**: Missing API keys, invalid settings
- **Download errors**: Network issues, invalid URLs
- **API errors**: Rate limits, authentication, quotas
- **Processing errors**: ffmpeg failures, file I/O
- **Validation errors**: Invalid output, corrupted data

### Recovery
- State saving for potential resume (coming in Phase 2)
- Automatic cleanup of temporary files
- Voice clone deletion on completion or failure

## Performance Considerations

### Bottlenecks
1. **Video Generation** (Stage 6): Slowest step, 2-5x real-time
2. **Voice Cloning** (Stage 4): One-time per video, ~1-2 minutes
3. **Transcription** (Stage 2): ~1/10 real-time
4. **Condensation** (Stage 3): Depends on transcript length

### Optimization Strategies
- Parallel API calls where possible (future)
- Chunked processing for long content
- Efficient audio normalization
- Fast-start video encoding
- Temporary file cleanup

### Resource Usage
- **Disk**: ~5-10GB per video (temporary)
- **Memory**: <2GB typical
- **Network**: High bandwidth for video download/upload
- **CPU**: Minimal (ffmpeg processes use CPU but are short)

## API Usage Patterns

### OpenAI (Whisper)
- Pay per minute of audio
- Single API call per transcription
- ~$0.006 per minute

### Anthropic (Claude)
- Pay per token (input + output)
- Single API call per video
- ~10K-50K tokens per video

### ElevenLabs
- Pay per character generated
- Voice clone: free (stored on account)
- Speech generation: ~$0.24 per 1K characters

### D-ID
- Pay per second of video generated
- Uploads: separate API calls
- Generation: polling until complete

## Security Considerations

### API Keys
- Stored in .env file (gitignored)
- Never logged or exposed
- Validated before use

### Downloaded Content
- Temporary storage only
- Automatic cleanup
- User owns all generated content

### User Privacy
- No data sent to NBJ Condenser servers (none exist)
- All processing via official APIs
- Logs contain no sensitive data

## Future Architecture Plans

### Phase 2: Graphics Integration
- Add scene detection module
- Graphics extraction pipeline
- Content-aware placement system
- Enhanced compositor

### Phase 3: Advanced Features
- Web interface (FastAPI backend)
- Database for job tracking
- Queue system for batch processing
- Multi-speaker support
- Local processing options

### Scalability
- Containerization (Docker)
- Cloud deployment options
- Distributed processing
- Caching system

## Testing Strategy

### Current Tests
- Unit tests for core functions
- Mock API responses
- File I/O validation

### Future Tests
- Integration tests (end-to-end)
- Performance benchmarks
- Quality metrics
- Regression tests

## Logging

### Levels
- **INFO**: Progress updates, major steps
- **WARNING**: Non-fatal issues, fallbacks
- **ERROR**: Failures, exceptions
- **DEBUG**: Detailed operation info (future)

### Output
- Console: Colored, user-friendly
- File (`nbj.log`): Detailed, technical

## Dependencies

### Core Runtime
- Python 3.10+
- ffmpeg, ffprobe

### Python Packages
- yt-dlp: Video downloading
- click: CLI framework
- pydantic: Configuration
- openai: Whisper API
- anthropic: Claude API
- elevenlabs: Voice cloning
- requests: HTTP client
- colorama: Terminal colors

### Optional
- pytest: Testing
- black: Code formatting
- mypy: Type checking

## Versioning

Current: **v0.1.0** (Phase 1)

Version scheme: MAJOR.MINOR.PATCH
- MAJOR: Breaking changes, major features
- MINOR: New features, backward compatible
- PATCH: Bug fixes, minor improvements
