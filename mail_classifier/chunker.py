"""
Smart email chunking with paragraph-aware splitting.
Respects token limits while preserving semantic coherence.
Uses character-based token approximation (no tiktoken dependency).
"""

import re
from typing import List, Dict, Tuple
from .constants import CHARS_PER_TOKEN, TOKEN_SAFETY_FACTOR, DEFAULT_MAX_TOKENS


class EmailChunker:
    """
    Intelligent email chunking that respects token limits.
    Uses approximation: 1 token ~ 4 characters (with 10% safety margin).
    """

    def __init__(self, max_tokens: int = DEFAULT_MAX_TOKENS, overlap_tokens: int = 200):
        """
        Args:
            max_tokens: Maximum tokens per chunk (default 32K for large context models)
            overlap_tokens: Overlap between chunks for context preservation
        """
        self.max_tokens = max_tokens
        self.overlap_tokens = overlap_tokens

        # Token approximation parameters (from constants)
        self.chars_per_token = CHARS_PER_TOKEN
        self.safety_factor = TOKEN_SAFETY_FACTOR

        # Effective limits accounting for safety
        self.effective_max_tokens = int(max_tokens * self.safety_factor)
        self.effective_overlap_tokens = overlap_tokens

    def count_tokens(self, text: str) -> int:
        """
        Count tokens in text using character approximation.

        Formula: tokens ≈ len(text) / 4
        Precision: ~85% (sufficient for context window management)

        Args:
            text: Text to count tokens for

        Returns:
            Estimated token count
        """
        if not text:
            return 0

        char_count = len(text)
        token_estimate = int(char_count / self.chars_per_token)

        return token_estimate

    def chunk_email(self, email_body: str, metadata: Dict = None) -> List[Dict]:
        """
        Chunk email into semantically coherent pieces.

        Strategy:
        1. Count total tokens
        2. If under limit, return as single chunk
        3. Otherwise, split by paragraphs (double newline)
        4. Group paragraphs until approaching token limit
        5. Maintain overlap for context preservation

        Args:
            email_body: Email body text
            metadata: Optional metadata to include in each chunk

        Returns:
            List of chunk dictionaries with text, token_count, metadata
        """
        if not email_body:
            return []

        if metadata is None:
            metadata = {}

        # Check if chunking needed
        total_tokens = self.count_tokens(email_body)
        if total_tokens <= self.effective_max_tokens:
            return [{
                'chunk_index': 0,
                'chunk_text': email_body,
                'token_count': total_tokens,
                'chunk_type': 'full',
                'metadata': metadata,
                'previous_overlap': None
            }]

        # Split into paragraphs
        paragraphs = self._split_paragraphs(email_body)

        if not paragraphs:
            # Fallback: return as single chunk even if oversized
            return [{
                'chunk_index': 0,
                'chunk_text': email_body,
                'token_count': total_tokens,
                'chunk_type': 'full',
                'metadata': metadata,
                'previous_overlap': None
            }]

        # Group paragraphs into chunks
        chunks = self._group_paragraphs(paragraphs, metadata)

        return chunks

    def _split_paragraphs(self, text: str) -> List[str]:
        """
        Split text into paragraphs.
        Handles various paragraph separators and email quote markers.

        Args:
            text: Text to split

        Returns:
            List of paragraph strings
        """
        # Normalize line endings
        text = text.replace('\r\n', '\n').replace('\r', '\n')

        # Split by double newline or common email markers
        # Patterns:
        # - Double newline: \n\n+
        # - Email headers: ^From:, ^Sent:, ^Subject:, ^To:
        # - Quote markers: ^>
        split_pattern = r'\n\n+|(?=^From:)|(?=^Sent:)|(?=^Subject:)|(?=^To:)|(?=^>)'

        paragraphs = re.split(split_pattern, text, flags=re.MULTILINE)

        # Filter empty paragraphs and strip whitespace
        paragraphs = [p.strip() for p in paragraphs if p.strip()]

        return paragraphs

    def _group_paragraphs(self, paragraphs: List[str], metadata: Dict) -> List[Dict]:
        """
        Group paragraphs into token-limited chunks with overlap.

        Args:
            paragraphs: List of paragraph strings
            metadata: Metadata to include in chunks

        Returns:
            List of chunk dictionaries
        """
        chunks = []
        current_chunk_paras = []
        current_tokens = 0
        overlap_buffer = []

        for para in paragraphs:
            para_tokens = self.count_tokens(para)

            # If single paragraph exceeds limit, split into sentences
            if para_tokens > self.effective_max_tokens:
                # Flush current chunk if any
                if current_chunk_paras:
                    chunks.append(self._create_chunk(
                        current_chunk_paras, overlap_buffer, metadata, len(chunks)
                    ))
                    current_chunk_paras = []
                    current_tokens = 0

                # Split large paragraph
                sentence_chunks = self._split_large_paragraph(para, metadata, len(chunks))
                chunks.extend(sentence_chunks)

                # Update overlap buffer with last sentences of last chunk
                if sentence_chunks:
                    last_chunk_text = sentence_chunks[-1]['chunk_text']
                    overlap_chars = int(self.effective_overlap_tokens * self.chars_per_token)
                    overlap_buffer = [last_chunk_text[-overlap_chars:]]

                continue

            # Check if adding paragraph exceeds limit
            if current_tokens + para_tokens > self.effective_max_tokens - self.effective_overlap_tokens:
                # Create chunk with current paragraphs
                chunks.append(self._create_chunk(
                    current_chunk_paras, overlap_buffer, metadata, len(chunks)
                ))

                # Start new chunk with overlap
                # Keep last 1-2 paragraphs as overlap (~200 tokens)
                overlap_text_chars = self.effective_overlap_tokens * self.chars_per_token
                overlap_buffer = self._get_overlap_paragraphs(
                    current_chunk_paras, overlap_text_chars
                )

                current_chunk_paras = overlap_buffer + [para]
                current_tokens = sum(self.count_tokens(p) for p in current_chunk_paras)
            else:
                current_chunk_paras.append(para)
                current_tokens += para_tokens

        # Add final chunk
        if current_chunk_paras:
            chunks.append(self._create_chunk(
                current_chunk_paras, overlap_buffer, metadata, len(chunks)
            ))

        return chunks

    def _get_overlap_paragraphs(self, paragraphs: List[str], target_chars: int) -> List[str]:
        """
        Get last few paragraphs to use as overlap, targeting specific character count.

        Args:
            paragraphs: List of paragraphs
            target_chars: Target character count for overlap

        Returns:
            List of paragraphs for overlap
        """
        if not paragraphs:
            return []

        overlap = []
        char_count = 0

        # Take paragraphs from end until we reach target chars
        for para in reversed(paragraphs):
            overlap.insert(0, para)
            char_count += len(para)
            if char_count >= target_chars:
                break

        # Limit to last 3 paragraphs max
        return overlap[-3:]

    def _create_chunk(self, paragraphs: List[str], overlap: List[str],
                     metadata: Dict, index: int) -> Dict:
        """
        Create chunk dictionary with metadata.

        Args:
            paragraphs: Paragraphs in this chunk
            overlap: Overlap paragraphs from previous chunk
            metadata: Metadata to include
            index: Chunk index

        Returns:
            Chunk dictionary
        """
        chunk_text = '\n\n'.join(paragraphs)
        overlap_text = '\n\n'.join(overlap) if overlap else None

        return {
            'chunk_index': index,
            'chunk_text': chunk_text,
            'token_count': self.count_tokens(chunk_text),
            'chunk_type': 'paragraph_group',
            'previous_overlap': overlap_text,
            'metadata': metadata
        }

    def _split_large_paragraph(self, paragraph: str, metadata: Dict,
                               start_index: int) -> List[Dict]:
        """
        Split large paragraph into sentence-based chunks.

        Args:
            paragraph: Large paragraph to split
            metadata: Metadata to include
            start_index: Starting chunk index

        Returns:
            List of chunk dictionaries
        """
        # Split by sentences (simple regex)
        sentence_pattern = r'(?<=[.!?])\s+'
        sentences = re.split(sentence_pattern, paragraph)

        if not sentences:
            # Fallback: split by character count
            return self._split_by_chars(paragraph, metadata, start_index)

        chunks = []
        current_sentences = []
        current_tokens = 0

        for sentence in sentences:
            sentence_tokens = self.count_tokens(sentence)

            # If single sentence exceeds limit, split by characters
            if sentence_tokens > self.effective_max_tokens:
                # Flush current
                if current_sentences:
                    chunks.append({
                        'chunk_index': start_index + len(chunks),
                        'chunk_text': ' '.join(current_sentences),
                        'token_count': current_tokens,
                        'chunk_type': 'sentence_group',
                        'metadata': metadata,
                        'previous_overlap': None
                    })
                    current_sentences = []
                    current_tokens = 0

                # Split oversized sentence
                char_chunks = self._split_by_chars(sentence, metadata, start_index + len(chunks))
                chunks.extend(char_chunks)
                continue

            # Check if adding sentence exceeds limit
            if current_tokens + sentence_tokens > self.effective_max_tokens - self.effective_overlap_tokens:
                # Create chunk
                chunks.append({
                    'chunk_index': start_index + len(chunks),
                    'chunk_text': ' '.join(current_sentences),
                    'token_count': current_tokens,
                    'chunk_type': 'sentence_group',
                    'metadata': metadata,
                    'previous_overlap': None
                })

                # Start new with overlap (last sentence)
                overlap_sentence = current_sentences[-1] if current_sentences else ''
                current_sentences = [overlap_sentence, sentence] if overlap_sentence else [sentence]
                current_tokens = sum(self.count_tokens(s) for s in current_sentences)
            else:
                current_sentences.append(sentence)
                current_tokens += sentence_tokens

        # Add final chunk
        if current_sentences:
            chunks.append({
                'chunk_index': start_index + len(chunks),
                'chunk_text': ' '.join(current_sentences),
                'token_count': current_tokens,
                'chunk_type': 'sentence_group',
                'metadata': metadata,
                'previous_overlap': None
            })

        return chunks

    def _split_by_chars(self, text: str, metadata: Dict, start_index: int) -> List[Dict]:
        """
        Fallback: split text by character count when semantic splitting fails.

        Args:
            text: Text to split
            metadata: Metadata to include
            start_index: Starting chunk index

        Returns:
            List of chunk dictionaries
        """
        max_chars = int(self.effective_max_tokens * self.chars_per_token)
        overlap_chars = int(self.effective_overlap_tokens * self.chars_per_token)

        chunks = []
        start = 0

        while start < len(text):
            end = start + max_chars
            chunk_text = text[start:end]

            chunks.append({
                'chunk_index': start_index + len(chunks),
                'chunk_text': chunk_text,
                'token_count': self.count_tokens(chunk_text),
                'chunk_type': 'character_split',
                'metadata': metadata,
                'previous_overlap': text[max(0, start - overlap_chars):start] if start > 0 else None
            })

            start = end - overlap_chars  # Move with overlap

        return chunks


# Convenience function
def chunk_email_text(email_body: str, max_tokens: int = 32000,
                     overlap_tokens: int = 200, metadata: Dict = None) -> List[Dict]:
    """
    Convenience function to chunk email text.

    Args:
        email_body: Email body text
        max_tokens: Maximum tokens per chunk
        overlap_tokens: Overlap between chunks
        metadata: Optional metadata

    Returns:
        List of chunk dictionaries
    """
    chunker = EmailChunker(max_tokens=max_tokens, overlap_tokens=overlap_tokens)
    return chunker.chunk_email(email_body, metadata=metadata)
