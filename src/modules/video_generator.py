"""Video generation module using D-ID API."""

import time
import requests
from pathlib import Path
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class VideoGenerator:
    """Generates talking head videos using D-ID API."""

    def __init__(self, api_key: str):
        """
        Initialize the video generator.

        Args:
            api_key: D-ID API key
        """
        self.api_key = api_key
        self.base_url = "https://api.d-id.com"
        self.headers = {
            "Authorization": f"Basic {api_key}",
            "Content-Type": "application/json"
        }

    def generate_video(
        self,
        source_url: str,
        audio_url: str,
        output_path: Path,
        driver_url: str = "bank://lively",
        max_wait_time: int = 600
    ) -> Path:
        """
        Generate talking head video from source image and audio.

        Args:
            source_url: URL to source image (face photo) or video
            audio_url: URL to audio file
            output_path: Path to save generated video
            driver_url: Animation driver (default: bank://lively)
            max_wait_time: Maximum time to wait for generation (seconds)

        Returns:
            Path to generated video file
        """
        try:
            logger.info("Starting video generation with D-ID")

            # Create the talk
            talk_data = {
                "source_url": source_url,
                "script": {
                    "type": "audio",
                    "audio_url": audio_url
                },
                "config": {
                    "driver_expressions": {
                        "expressions": [{"expression": driver_url, "start_frame": 0}]
                    },
                    "stitch": True  # Better quality
                }
            }

            # Submit the generation request
            response = requests.post(
                f"{self.base_url}/talks",
                headers=self.headers,
                json=talk_data
            )
            response.raise_for_status()

            talk_id = response.json()["id"]
            logger.info(f"Video generation started: {talk_id}")

            # Poll for completion
            video_url = self._wait_for_completion(talk_id, max_wait_time)

            # Download the video
            logger.info("Downloading generated video")
            self._download_video(video_url, output_path)

            logger.info(f"Video generation completed: {output_path}")
            return output_path

        except requests.exceptions.RequestException as e:
            logger.error(f"D-ID API error: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Response: {e.response.text}")
            raise RuntimeError(f"Failed to generate video: {e}")

        except Exception as e:
            from ..utils.audio_utils import extract_api_error_message
            from ..utils.exceptions import ApiError
            from colorama import Fore, Style
            error_msg = extract_api_error_message(e, "D-ID")
            if error_msg:
                print(f"\n{Fore.RED}{error_msg}{Style.RESET_ALL}\n")
                raise ApiError(error_msg) from None
            else:
                logger.error(f"Video generation failed: {e}")
                raise RuntimeError(f"Failed to generate video: {e}")

    def _wait_for_completion(self, talk_id: str, max_wait_time: int) -> str:
        """
        Wait for video generation to complete.

        Args:
            talk_id: D-ID talk ID
            max_wait_time: Maximum wait time in seconds

        Returns:
            URL to generated video

        Raises:
            TimeoutError if generation takes too long
            RuntimeError if generation fails
        """
        start_time = time.time()
        poll_interval = 5  # seconds

        while time.time() - start_time < max_wait_time:
            response = requests.get(
                f"{self.base_url}/talks/{talk_id}",
                headers=self.headers
            )
            response.raise_for_status()

            status_data = response.json()
            status = status_data.get("status")

            logger.info(f"Status: {status}")

            if status == "done":
                return status_data["result_url"]

            elif status == "error":
                error_msg = status_data.get("error", {}).get("description", "Unknown error")
                raise RuntimeError(f"Video generation failed: {error_msg}")

            elif status in ["created", "started"]:
                # Still processing
                time.sleep(poll_interval)

            else:
                logger.warning(f"Unknown status: {status}")
                time.sleep(poll_interval)

        raise TimeoutError(f"Video generation timed out after {max_wait_time}s")

    def _download_video(self, video_url: str, output_path: Path):
        """
        Download video from URL.

        Args:
            video_url: URL to video
            output_path: Path to save video
        """
        response = requests.get(video_url, stream=True)
        response.raise_for_status()

        with open(output_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

    def generate_from_local_files(
        self,
        source_image_path: Path,
        audio_path: Path,
        output_path: Path,
        **kwargs
    ) -> Path:
        """
        Generate video from local files by uploading them first.

        Args:
            source_image_path: Path to source image
            audio_path: Path to audio file
            output_path: Path to save generated video
            **kwargs: Additional arguments for generate_video

        Returns:
            Path to generated video file
        """
        logger.info("Uploading source image and audio")

        # Upload source image
        source_url = self._upload_file(source_image_path)

        # Upload audio
        audio_url = self._upload_file(audio_path)

        # Generate video
        return self.generate_video(source_url, audio_url, output_path, **kwargs)

    def _upload_file(self, file_path: Path) -> str:
        """
        Upload file to D-ID and get URL.

        Args:
            file_path: Path to file to upload

        Returns:
            URL to uploaded file
        """
        try:
            with open(file_path, 'rb') as f:
                files = {'file': (file_path.name, f)}
                headers = {"Authorization": self.headers["Authorization"]}

                response = requests.post(
                    f"{self.base_url}/images",
                    headers=headers,
                    files=files
                )
                response.raise_for_status()

                upload_url = response.json()["url"]
                logger.info(f"Uploaded {file_path.name}: {upload_url}")
                return upload_url

        except Exception as e:
            logger.error(f"File upload failed: {e}")
            raise RuntimeError(f"Failed to upload file: {e}")

    def get_credits(self) -> Dict[str, Any]:
        """
        Get remaining API credits.

        Returns:
            Dictionary with credit information
        """
        try:
            response = requests.get(
                f"{self.base_url}/credits",
                headers=self.headers
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
            logger.error(f"Failed to get credits: {e}")
            return {}


class HeyGenVideoGenerator:
    """Alternative video generator using HeyGen API."""

    def __init__(self, api_key: str):
        """
        Initialize HeyGen video generator.

        Args:
            api_key: HeyGen API key
        """
        self.api_key = api_key
        self.base_url = "https://api.heygen.com/v1"
        self.headers = {
            "X-Api-Key": api_key,
            "Content-Type": "application/json"
        }

    def generate_video(
        self,
        avatar_id: str,
        audio_path: Path,
        output_path: Path,
        max_wait_time: int = 600
    ) -> Path:
        """
        Generate video using HeyGen.

        Note: This is a simplified implementation. Full HeyGen integration
        would require more complex setup including avatar creation.

        Args:
            avatar_id: HeyGen avatar ID
            audio_path: Path to audio file
            output_path: Path to save video
            max_wait_time: Maximum wait time

        Returns:
            Path to generated video
        """
        # Note: HeyGen API implementation would go here
        # This is a placeholder for the actual implementation
        raise NotImplementedError("HeyGen integration coming in next update")
