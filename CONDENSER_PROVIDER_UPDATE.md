# Content Condenser Provider Update

## Summary

Added support for using **OpenAI GPT-4o** as an alternative to Claude for content condensation. OpenAI is now the **default provider** due to better reliability (no 529 overload errors).

## Changes Made

### 1. Configuration (`src/config.py`)
- Added new setting: `condenser_service` (default: `"openai"`)
- Options: `"openai"` or `"claude"`

### 2. Condenser Module (`src/modules/condenser.py`)
- **Multi-provider support**: Now supports both Claude and OpenAI
- **Automatic retry logic**: Exponential backoff for transient errors (529, rate limits, timeouts)
- **Provider-specific optimizations**:
  - **OpenAI**: Uses `gpt-4o` with JSON mode for structured output
  - **Claude**: Uses `claude-sonnet-4-20250514` with message API

### 3. Pipeline (`src/pipeline.py`)
- Updated to use the configured provider automatically
- Passes both API keys to condenser for flexibility

### 4. Environment Variables (`.env.example`)
- Documented new `CONDENSER_SERVICE` option
- Updated API key descriptions

## Usage

### Option 1: Use OpenAI (Default - Recommended)

```bash
# In your .env file
CONDENSER_SERVICE=openai
OPENAI_API_KEY=sk-...
```

**Benefits:**
- More reliable (no overload errors)
- Faster response times
- JSON mode ensures valid output
- Uses GPT-4o model

### Option 2: Use Claude

```bash
# In your .env file
CONDENSER_SERVICE=claude
ANTHROPIC_API_KEY=sk-ant-...
```

**Benefits:**
- Longer context window
- Different AI perspective on condensation
- May produce different editing style

## Retry Logic

Both providers now include automatic retry with exponential backoff:

- **Max retries**: 5 attempts
- **Backoff schedule**: 2s → 4s → 8s → 16s → 32s
- **Total retry time**: Up to 62 seconds
- **Retryable errors**: 529 Overloaded, rate limits, timeouts, connection errors

## Troubleshooting

### Claude 529 Errors
If you see "Error code: 529 - Overloaded" repeatedly:
1. Switch to OpenAI: `CONDENSER_SERVICE=openai` in `.env`
2. The retry logic will attempt 5 times before failing
3. OpenAI has better availability and no overload issues

### Cost Comparison

**OpenAI GPT-4o** (30-min video):
- Input: ~50K tokens × $2.50/1M = $0.13
- Output: ~10K tokens × $10/1M = $0.10
- **Total: ~$0.23**

**Claude Sonnet** (30-min video):
- Input: ~50K tokens × $3/1M = $0.15
- Output: ~10K tokens × $15/1M = $0.15
- **Total: ~$0.30**

Both are very affordable, but OpenAI is slightly cheaper and more reliable.

## Migration

No action required! The system defaults to OpenAI now. If you were using Claude and want to continue:

```bash
# Add to .env
CONDENSER_SERVICE=claude
```

## Technical Details

### OpenAI Integration
- Model: `gpt-4o` (latest GPT-4 optimized)
- Response format: JSON mode (guaranteed valid JSON)
- System prompt: Optimized for content condensation
- Temperature: 0.3 (consistent output)

### Claude Integration
- Model: `claude-sonnet-4-20250514` (latest Sonnet)
- Response format: Text with JSON extraction
- Temperature: 0.3 (consistent output)
- Fallback JSON parsing from markdown code blocks

## Logs

The condenser now logs which provider is being used:

```
Starting content condensation (provider: openai, model: gpt-4o, aggressiveness: 5/10)
```

Or with retries:

```
Starting content condensation (provider: openai, model: gpt-4o, aggressiveness: 5/10)
API request failed (attempt 1/6): Error code: 529 - Overloaded. Retrying in 2.0s...
API request failed (attempt 2/6): Error code: 529 - Overloaded. Retrying in 4.0s...
[Success on attempt 3]
Condensation completed: 45.2% reduction, 30.0min -> 16.4min
```
