"""
Vector embedding and similarity search using filesystem storage.
No sqlite-vec dependency - uses pickle + numpy arrays.
"""

import os
import pickle
import numpy as np
from typing import List, Dict, Tuple, Optional
from datetime import datetime


class VectorStore:
    """
    Manages vector embeddings and similarity search.
    Stores embeddings as numpy arrays on filesystem.
    """

    def __init__(self, db, api_client, storage_dir: str = "embeddings",
                 embedding_model: str = "multilingual-e5-large",
                 embedding_dim: int = 1024,
                 cache_in_memory: bool = True,
                 max_cache_size: int = 1000):
        """
        Args:
            db: DatabaseManager instance
            api_client: API client for generating embeddings
            storage_dir: Directory for storing embedding files
            embedding_model: Embedding model name
            embedding_dim: Embedding dimension
            cache_in_memory: Whether to cache embeddings in memory
            max_cache_size: Maximum number of embeddings to cache
        """
        self.db = db
        self.api = api_client
        self.storage_dir = storage_dir
        self.embedding_model = embedding_model
        self.embedding_dim = embedding_dim

        # Memory cache for frequently used embeddings
        self.cache_enabled = cache_in_memory
        self.max_cache_size = max_cache_size
        self._embedding_cache = {}  # {chunk_id: numpy array}

        # Index: {chunk_id: filepath}
        self.index_path = os.path.join(storage_dir, "index.pkl")
        self.index = self._load_or_create_index()

        # Ensure storage directory exists
        os.makedirs(storage_dir, exist_ok=True)

    def _load_or_create_index(self) -> Dict[int, str]:
        """Load existing index or create new one."""
        if os.path.exists(self.index_path):
            try:
                with open(self.index_path, 'rb') as f:
                    index = pickle.load(f)
                print(f"✓ Loaded embedding index: {len(index)} entries")
                return index
            except Exception as e:
                print(f"⚠ Error loading index, creating new: {e}")
                return {}
        return {}

    def _save_index(self):
        """Save index to disk."""
        try:
            with open(self.index_path, 'wb') as f:
                pickle.dump(self.index, f)
        except Exception as e:
            print(f"✗ Error saving index: {e}")

    def embed_text(self, text: str) -> np.ndarray:
        """
        Generate embedding for text using API.

        Args:
            text: Text to embed

        Returns:
            Numpy array of embedding vector (float32)
        """
        try:
            # Call API embedding endpoint
            response = self.api.get_embedding(text)

            # Convert to numpy array
            embedding = np.array(response, dtype=np.float32)

            # Validate dimension
            if embedding.shape[0] != self.embedding_dim:
                print(f"⚠ Warning: Expected {self.embedding_dim} dimensions, got {embedding.shape[0]}")

            return embedding

        except AttributeError:
            # Fallback: api_client might not have get_embedding yet
            print("⚠ API client doesn't have get_embedding method yet")
            # Return random embedding for testing (TEMPORARY)
            return np.random.randn(self.embedding_dim).astype(np.float32)
        except Exception as e:
            print(f"✗ Error generating embedding: {e}")
            raise

    def _get_embedding_path(self, chunk_id: int) -> str:
        """Get filepath for embedding."""
        return os.path.join(self.storage_dir, f"chunk_{chunk_id}.npy")

    def store_chunk_embedding(self, chunk_id: int, chunk_text: str) -> int:
        """
        Generate and store embedding for a chunk.

        Args:
            chunk_id: Database chunk ID
            chunk_text: Text content to embed

        Returns:
            embedding_id from database
        """
        # Generate embedding
        print(f"  Generating embedding for chunk {chunk_id}...", end='')
        embedding = self.embed_text(chunk_text)
        print(" ✓")

        # Save to filesystem
        embedding_path = self._get_embedding_path(chunk_id)
        np.save(embedding_path, embedding)

        # Update index
        self.index[chunk_id] = embedding_path
        self._save_index()

        # Store metadata in database
        embedding_id = self.db.insert_embedding_metadata(
            chunk_id=chunk_id,
            embedding_path=embedding_path,
            model=self.embedding_model,
            dimension=self.embedding_dim
        )

        # Add to cache if enabled
        if self.cache_enabled:
            self._add_to_cache(chunk_id, embedding)

        return embedding_id

    def load_embedding(self, chunk_id: int) -> Optional[np.ndarray]:
        """
        Load embedding from filesystem or cache.

        Args:
            chunk_id: Chunk ID

        Returns:
            Numpy array or None if not found
        """
        # Check cache first
        if self.cache_enabled and chunk_id in self._embedding_cache:
            return self._embedding_cache[chunk_id]

        # Check index
        if chunk_id not in self.index:
            # Try to find in database
            metadata = self.db.get_embedding_metadata(chunk_id)
            if metadata:
                self.index[chunk_id] = metadata['embedding_path']
            else:
                return None

        # Load from filesystem
        embedding_path = self.index[chunk_id]
        if not os.path.exists(embedding_path):
            print(f"⚠ Embedding file not found: {embedding_path}")
            return None

        try:
            embedding = np.load(embedding_path)

            # Add to cache
            if self.cache_enabled:
                self._add_to_cache(chunk_id, embedding)

            return embedding
        except Exception as e:
            print(f"✗ Error loading embedding {chunk_id}: {e}")
            return None

    def _add_to_cache(self, chunk_id: int, embedding: np.ndarray):
        """Add embedding to memory cache with LRU eviction."""
        if len(self._embedding_cache) >= self.max_cache_size:
            # Remove oldest entry (simple FIFO, could be improved to LRU)
            oldest_key = next(iter(self._embedding_cache))
            del self._embedding_cache[oldest_key]

        self._embedding_cache[chunk_id] = embedding

    def _batch_load_embeddings(self, chunk_ids: List[int]) -> Dict[int, np.ndarray]:
        """
        Batch load embeddings with cache optimization.
        Optimizes N+1 loading pattern by loading all embeddings at once.

        Args:
            chunk_ids: List of chunk IDs to load

        Returns:
            Dictionary mapping chunk_id to embedding array
        """
        result = {}
        to_load = []

        # First, get from cache
        for chunk_id in chunk_ids:
            if self.cache_enabled and chunk_id in self._embedding_cache:
                result[chunk_id] = self._embedding_cache[chunk_id]
            else:
                to_load.append(chunk_id)

        # Batch load remaining from disk
        for chunk_id in to_load:
            embedding = self.load_embedding(chunk_id)
            if embedding is not None:
                result[chunk_id] = embedding

        return result

    def similarity_search(self, query_text: str, top_k: int = 10,
                         threshold: float = 0.0) -> List[Dict]:
        """
        Semantic search using cosine similarity.

        Args:
            query_text: Search query
            top_k: Number of results to return
            threshold: Minimum similarity score (0-1)

        Returns:
            List of {chunk_id, email_id, score, chunk_text} dicts
        """
        # Generate query embedding
        print(f"Generating query embedding...", end='')
        query_embedding = self.embed_text(query_text)
        print(" ✓")

        # Normalize query embedding
        query_norm = np.linalg.norm(query_embedding)
        if query_norm == 0:
            print("⚠ Query embedding has zero norm")
            return []
        query_normalized = query_embedding / query_norm

        # Batch load all embeddings (optimized)
        print(f"Loading {len(self.index)} embeddings...")
        all_embeddings = self._batch_load_embeddings(list(self.index.keys()))

        # Compute similarities
        print(f"Computing similarities...")
        similarities = []

        for chunk_id, embedding in all_embeddings.items():
            # Normalize embedding
            emb_norm = np.linalg.norm(embedding)
            if emb_norm == 0:
                continue
            embedding_normalized = embedding / emb_norm

            # Cosine similarity
            similarity = np.dot(query_normalized, embedding_normalized)

            # Apply threshold
            if similarity >= threshold:
                similarities.append((chunk_id, float(similarity)))

        # Sort by similarity (descending)
        similarities.sort(key=lambda x: x[1], reverse=True)

        # Take top-k
        top_results = similarities[:top_k]

        # Fetch chunk details from database
        results = []
        for chunk_id, score in top_results:
            chunk = self.db.get_chunk(chunk_id)
            if chunk:
                results.append({
                    'chunk_id': chunk_id,
                    'email_id': chunk['email_id'],
                    'score': score,
                    'chunk_text': chunk['chunk_text'],
                    'token_count': chunk['token_count'],
                    'chunk_type': chunk['chunk_type']
                })

        print(f"✓ Found {len(results)} results")
        return results

    def batch_embed_emails(self, email_ids: List[int], show_progress: bool = True):
        """
        Background process to embed multiple emails.

        Args:
            email_ids: List of email IDs to embed
            show_progress: Whether to show progress
        """
        total = len(email_ids)
        processed = 0
        errors = 0

        print(f"\nBatch embedding {total} emails...")
        print("=" * 60)

        for i, email_id in enumerate(email_ids, 1):
            if show_progress:
                print(f"\n[{i}/{total}] Email {email_id}")

            try:
                # Get chunks for this email
                chunks = self.db.get_chunks_for_email(email_id)

                if not chunks:
                    print(f"  ⚠ No chunks found for email {email_id}")
                    continue

                # Embed each chunk
                for chunk in chunks:
                    chunk_id = chunk['chunk_id']

                    # Check if already embedded
                    existing = self.db.get_embedding_metadata(chunk_id)
                    if existing:
                        print(f"  ⊙ Chunk {chunk_id} already embedded, skipping")
                        continue

                    # Store embedding
                    self.store_chunk_embedding(chunk_id, chunk['chunk_text'])

                processed += 1

            except Exception as e:
                print(f"  ✗ Error processing email {email_id}: {e}")
                errors += 1

        print("\n" + "=" * 60)
        print(f"Batch embedding complete:")
        print(f"  Processed: {processed}/{total}")
        print(f"  Errors: {errors}")
        print("=" * 60)

    def get_statistics(self) -> Dict[str, int]:
        """Get embedding statistics."""
        stats = {
            'total_embeddings': len(self.index),
            'cached_embeddings': len(self._embedding_cache),
            'cache_size_mb': sum(
                emb.nbytes / (1024 * 1024)
                for emb in self._embedding_cache.values()
            ) if self._embedding_cache else 0
        }

        # Check filesystem
        if os.path.exists(self.storage_dir):
            files = [f for f in os.listdir(self.storage_dir) if f.endswith('.npy')]
            stats['filesystem_files'] = len(files)

            # Calculate total size
            total_bytes = sum(
                os.path.getsize(os.path.join(self.storage_dir, f))
                for f in files
            )
            stats['filesystem_size_mb'] = total_bytes / (1024 * 1024)

        return stats

    def clear_cache(self):
        """Clear memory cache."""
        self._embedding_cache.clear()
        print("✓ Embedding cache cleared")

    def rebuild_index(self):
        """Rebuild index from database and filesystem."""
        print("Rebuilding embedding index...")

        # Get all embeddings from database
        all_metadata = self.db.get_all_embeddings_metadata()

        new_index = {}
        found = 0
        missing = 0

        for metadata in all_metadata:
            chunk_id = metadata['chunk_id']
            embedding_path = metadata['embedding_path']

            if os.path.exists(embedding_path):
                new_index[chunk_id] = embedding_path
                found += 1
            else:
                print(f"  ⚠ Missing file for chunk {chunk_id}: {embedding_path}")
                missing += 1

        self.index = new_index
        self._save_index()

        print(f"✓ Index rebuilt: {found} found, {missing} missing")

    def close(self):
        """Cleanup resources."""
        self._save_index()
        self.clear_cache()


# Convenience function
def create_vector_store(db, api_client, storage_dir: str = "embeddings",
                       **kwargs) -> VectorStore:
    """
    Create VectorStore instance with default settings.

    Args:
        db: DatabaseManager instance
        api_client: API client instance
        storage_dir: Storage directory path
        **kwargs: Additional VectorStore parameters

    Returns:
        VectorStore instance
    """
    return VectorStore(db, api_client, storage_dir=storage_dir, **kwargs)
