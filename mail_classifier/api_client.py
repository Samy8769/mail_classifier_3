"""
API client module for Paradigm/OpenAI-compatible API.
Handles API calls with configuration from JSON.

Extracted from lines 15-26, 197-218 of original mail_classification.py
"""

import os
import ssl
import openai
import httpx
from typing import Dict, Any
from .logger import get_logger

logger = get_logger('api_client')


class APIError(Exception):
    """Exception raised for API errors."""
    pass


class ParadigmAPIClient:
    """Client for Paradigm API (OpenAI-compatible)."""

    def __init__(self, api_config: Dict[str, Any], proxy_config: Dict[str, Any]):
        """
        Initialize Paradigm API client.

        Args:
            api_config: API configuration (base_url, api_key, model, temperature, verify_ssl)
            proxy_config: Proxy configuration (http, https, no_proxy)
        """

        self.base_url = api_config['base_url']
        self.api_key = api_config['api_key']
        self.model = api_config['model']
        self.temperature = api_config['temperature']
        self.verify_ssl = api_config.get('verify_ssl', False)

        # Create SSL context using system certificates
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.load_default_certs()

        # Configure proxy settings
        self._configure_proxy(proxy_config)

        # Create persistent OpenAI client
        self.client = self._create_client()

    def _configure_proxy(self, proxy_config: Dict[str, Any]):
        """
        Configure proxy environment variables.

        Args:
            proxy_config: Proxy configuration dictionary
        """
        if proxy_config.get('http'):
            os.environ["HTTP_PROXY"] = proxy_config['http']
        if proxy_config.get('https'):
            os.environ["HTTPS_PROXY"] = proxy_config['https']
        if proxy_config.get('no_proxy'):
            os.environ["NO_PROXY"] = proxy_config['no_proxy']

    def _create_client(self) -> openai.OpenAI:
        """
        Create OpenAI client with custom configuration.

        Returns:
            Configured OpenAI client
        """
        return openai.OpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
            http_client=httpx.Client(verify=self.verify_ssl)
        )

    def call_paradigm(self, prompt: str, content: str) -> str:
        """
        Call Paradigm API with chat completion.
        Replaces CallAPI_PARADIGM from lines 197-218.

        Args:
            prompt: System prompt
            content: User content

        Returns:
            API response content

        Raises:
            APIError: If API call fails
        """
        if not prompt or not isinstance(prompt, str):
            raise APIError("Invalid prompt: expected non-empty string")
        if not content and not isinstance(content, str):
            raise APIError("Invalid content: expected a string")

        try:
            messages = [
                {"role": "system", "content": prompt},
                {"role": "user", "content": content}
            ]

            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.temperature
            )

            return response.choices[0].message.content

        except Exception as e:
            raise APIError(f"Paradigm API call failed: {str(e)}") from e

    def call_completions(self, prompt: str, text: str) -> str:
        """
        Alternative completion API (for future use).
        Based on lines 188-194 of original script.

        Args:
            prompt: Prompt text
            text: Text to process

        Returns:
            API response text

        Raises:
            APIError: If API call fails
        """
        try:
            full_prompt = f"{prompt}:\n\nTexte à chunker\n\n{text}"

            response = self.client.completions.create(
                model=self.model,
                prompt=full_prompt,
                temperature=self.temperature
            )

            return response.choices[0].text.strip()

        except Exception as e:
            raise APIError(f"Paradigm completions call failed: {str(e)}") from e

    def get_embedding(self, text: str, model: str = None) -> list:
        """
        Generate embedding using Paradigm API with multilingual-e5-large model.

        Args:
            text: Text to embed (any language, optimized for French/English)
            model: Optional embedding model (defaults to multilingual-e5-large)

        Returns:
            List of float values (embedding vector, 1024 dimensions for e5-large)

        Raises:
            APIError: If API call fails
        """
        if model is None:
            model = "multilingual-e5-large"

        try:
            response = self.client.embeddings.create(
                model=model,
                input=text
            )

            return response.data[0].embedding

        except Exception as e:
            # If multilingual-e5-large not available, try fallback
            if "multilingual-e5-large" in str(e) and model == "multilingual-e5-large":
                logger.warning("multilingual-e5-large not available, trying text-embedding-ada-002")
                try:
                    response = self.client.embeddings.create(
                        model="text-embedding-ada-002",
                        input=text
                    )
                    return response.data[0].embedding
                except Exception as e2:
                    raise APIError(f"Embedding API call failed (both models): {str(e2)}") from e2

            raise APIError(f"Embedding API call failed: {str(e)}") from e
