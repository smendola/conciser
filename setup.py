"""Setup script for Conciser."""

from setuptools import setup, find_packages
from pathlib import Path

# Read README for long description
readme_file = Path(__file__).parent / "README.md"
long_description = readme_file.read_text(encoding="utf-8") if readme_file.exists() else ""

setup(
    name="conciser",
    version="0.1.0",
    description="AI-powered video condensation tool",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Your Name",
    author_email="your.email@example.com",
    url="https://github.com/yourusername/conciser",
    packages=find_packages(),
    install_requires=[
        "yt-dlp>=2024.0.0",
        "click>=8.1.0",
        "pydantic>=2.0.0",
        "pydantic-settings>=2.0.0",
        "python-dotenv>=1.0.0",
        "openai>=1.12.0",
        "anthropic>=0.18.0",
        "elevenlabs>=0.2.0",
        "requests>=2.31.0",
        "ffmpeg-python>=0.2.0",
        "moviepy>=1.0.3",
        "pydub>=0.25.1",
        "colorama>=0.4.6",
        "tqdm>=4.66.0",
        "tenacity>=8.2.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-cov>=4.0.0",
            "black>=23.0.0",
            "flake8>=6.0.0",
            "mypy>=1.0.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "conciser=src.main:cli",
        ],
    },
    python_requires=">=3.10",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Intended Audience :: End Users/Desktop",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Multimedia :: Video",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
    ],
    keywords="video ai condensation summarization voice-cloning video-generation",
)
