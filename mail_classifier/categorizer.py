"""
Categorization module for AI-based email classification.
Implements multi-axis classification pipeline with smart caching.
Enhanced v2.0 with chunking, database storage, and validation.

Decomposes TrouverCategories() function from lines 221-304 of original mail_classification.py
"""

from typing import List, Dict, Any, Optional
from .config import Config, AxisConfig
from .api_client import ParadigmAPIClient
from .state_manager import StateManager
from .utils import parse_categories
from .logger import get_logger

logger = get_logger('categorizer')


class Categorizer:
    """AI-powered email categorizer with multi-axis classification."""

    def __init__(self, config: Config, api_client: ParadigmAPIClient,
                 state_manager: StateManager,
                 db=None, chunker=None, validator=None, vector_store=None):
        """
        Initialize categorizer.

        Args:
            config: Configuration object
            api_client: API client for making AI calls
            state_manager: State manager for caching
            db: Optional DatabaseManager for enhanced features (v2.0)
            chunker: Optional EmailChunker for long emails (v2.0)
            validator: Optional TagValidator for validation (v2.0)
            vector_store: Optional VectorStore for embeddings (v2.0)
        """
        self.config = config
        self.api = api_client
        self.state = state_manager
        self.axes = config.classification['axes']

        # Enhanced v2.0 components
        self.db = db
        self.chunker = chunker
        self.validator = validator
        self.vector_store = vector_store

        # Feature flags from config
        self.use_chunking = chunker is not None and self._get_config_value('chunking', 'enabled', False)
        self.use_database = db is not None and self._get_config_value('database', 'enabled', False)
        self.use_validation = validator is not None and self._get_config_value('validation', 'enabled', True)
        self.use_embeddings = vector_store is not None and self._get_config_value('embeddings', 'enabled', False)

    def _get_config_value(self, section: str, key: str, default=None):
        """Safely get config value."""
        try:
            if hasattr(self.config, section):
                section_data = getattr(self.config, section)
                if isinstance(section_data, dict):
                    return section_data.get(key, default)
            return default
        except Exception as e:
            logger.debug(f"Error accessing config {section}.{key}: {e}")
            return default

    def categorize_conversation(self, conversation_id: str,
                                emails: List[Dict[str, Any]]) -> List[str]:
        """
        Main classification pipeline with smart processing.
        Replaces TrouverCategories from lines 221-304.
        Enhanced v2.0 with chunking, database storage, and validation.

        Args:
            conversation_id: Conversation ID
            emails: List of email data dictionaries

        Returns:
            List of categories
        """
        # Check if already processed (NEW - Requirement 4: smart processing)
        if self.state.is_conversation_processed(conversation_id):
            cached = self.state.get_cached_categories(conversation_id)
            if cached:
                logger.info(f"Conversation {conversation_id} already processed, using cache")
                return cached

        # Boucle dans les conversations (preserve comment from line 222)
        email_summaries = self._generate_summaries(emails)

        # Run dynamic classification pipeline
        categories = self._run_classification_pipeline(email_summaries)

        # v3.0: Apply inference rules from database
        if self.use_database and self.db:
            try:
                categories = self.db.apply_inference_rules(categories)
            except Exception as e:
                logger.warning(f"Inference rules error: {e}")

        # v3.2: Tag validation (deterministic DB check + optional LLM)
        # Always run if validator and DB are available, regardless of validation flag
        if self.validator and self.db:
            summaries_str = str(email_summaries)
            categories = self.validator.validate_and_correct(
                conversation_id, summaries_str, categories
            )
        elif self.use_validation and self.validator:
            # Fallback: LLM-only validation without DB
            summaries_str = str(email_summaries)
            categories = self.validator.validate_and_correct(
                conversation_id, summaries_str, categories
            )

        # V2.0: Store in database if enabled
        if self.use_database and self.db:
            self._store_classification_in_db(conversation_id, emails, categories)

        # Cache results
        self.state.cache_conversation(conversation_id, categories)

        return categories

    def _generate_summaries(self, emails: List[Dict[str, Any]]) -> List[str]:
        """
        Generate AI summaries for each email in conversation.
        Enhanced v2.0 with smart chunking for long emails.
        Extracted from lines 226-246 of original script.

        Args:
            emails: List of email data dictionaries

        Returns:
            List of email summaries
        """
        summaries = []

        for i, email in enumerate(emails, start=1):
            # Reconstitution d'une conversation à partir des emails (preserve comment from line 230)
            email_text = self._format_email_for_llm(email, i)

            # V2.0: Check if chunking needed
            if self.use_chunking and self.chunker:
                token_count = self.chunker.count_tokens(email_text)
                max_tokens = self.chunker.effective_max_tokens

                if token_count > max_tokens:
                    logger.info(f"Email {i} exceeds token limit ({token_count} tokens). Chunking...")
                    summary = self._summarize_with_chunking(email, i)
                    summaries.append(summary)
                    continue

            # Faire un résumé de l'email via LLM (preserve comment from line 242)
            resume_axis = self.config.get_axis_by_name('resume')
            if resume_axis:
                summary = self.api.call_paradigm(
                    resume_axis.prompt,
                    email_text
                )
                summaries.append(summary)
            else:
                # If no resume axis, use raw email
                summaries.append(email_text)

        return summaries

    def _summarize_with_chunking(self, email: Dict[str, Any], index: int) -> str:
        """
        Summarize long email with chunking (v2.0).

        Args:
            email: Email data
            index: Email number

        Returns:
            Combined summary
        """
        # Chunk the email body
        chunks = self.chunker.chunk_email(
            email['body'],
            metadata={
                'subject': email['subject'],
                'sender': email['sender_email'],
                'index': index
            }
        )

        logger.info(f"Created {len(chunks)} chunks ({', '.join([str(c['token_count']) for c in chunks])} tokens)")

        # Summarize each chunk
        resume_axis = self.config.get_axis_by_name('resume')
        if not resume_axis:
            # No resume axis, combine chunks
            return f"[Multi-chunk email {index}]\n" + '\n\n'.join([c['chunk_text'][:500] for c in chunks])

        chunk_summaries = []
        for j, chunk in enumerate(chunks, 1):
            # Format chunk for LLM
            chunk_text = self._format_chunk_for_llm(chunk, index, j)

            # Summarize chunk
            chunk_summary = self.api.call_paradigm(
                resume_axis.prompt,
                chunk_text
            )
            chunk_summaries.append(chunk_summary)

        # Combine summaries
        combined = f"[Multi-chunk email {index} with {len(chunks)} chunks]\n\n"
        combined += '\n\n'.join([f"Chunk {i+1}: {s}" for i, s in enumerate(chunk_summaries)])

        return combined

    def _format_chunk_for_llm(self, chunk: Dict, email_index: int, chunk_index: int) -> str:
        """
        Format chunk for LLM processing (v2.0).

        Args:
            chunk: Chunk dictionary
            email_index: Email number
            chunk_index: Chunk number

        Returns:
            Formatted chunk text
        """
        metadata = chunk.get('metadata', {})
        return (
            f"----------\n\n**Mail #{email_index} - Chunk {chunk_index}/{chunk.get('chunk_index', 0)+1}**\n"
            f"***Subject***: {metadata.get('subject', 'N/A')}\n"
            f"***Sender***: {metadata.get('sender', 'N/A')}\n"
            f"***Type***: {chunk['chunk_type']} ({chunk['token_count']} tokens)\n\n"
            f"{chunk['chunk_text']}"
        )

    def _format_email_for_llm(self, email: Dict[str, Any], index: int) -> str:
        """
        Format email data for LLM processing.
        Extracted from lines 232-240 of original script.

        Args:
            email: Email data dictionary
            index: Email number in conversation

        Returns:
            Formatted email text
        """
        return (
            f"----------\n\n**Mail # {index}\n"
            f"***TOPIC***: {email['conversation_topic']}\n"
            f"***Subject***: {email['subject']}"
            f"***Body***: {email['body']}"
            f"***Received Time***: {email['received_time']}"
            f"***Recipients***: {email['recipients']}"
            f"***Sender Email***: {email['sender_email']}"
        )

    def _run_classification_pipeline(self, email_summaries: List[str]) -> List[str]:
        """
        Dynamic multi-axis classification pipeline.
        Replaces hardcoded type→projet→fournisseur→equipement→processus from lines 248-273.
        Now driven by YAML configuration.

        Args:
            email_summaries: List of email summaries

        Returns:
            List of all categories
        """
        context = {}  # Store results from previous axes
        all_categories = []

        for axis in self.axes:
            if axis.name == 'resume':
                continue  # Already processed

            # Proposer les catégories (preserve comment from line 248)
            categories_str = self._classify_axis(axis, email_summaries, context)

            # Store in context for dependent axes
            context[axis.name] = categories_str

            # Transformation en liste (preserve comment from line 289)
            category_list = self._parse_categories(categories_str)
            all_categories.extend(category_list)

            logger.info(f"AI {axis.name} done")

        return all_categories

    def _classify_axis(self, axis: AxisConfig, email_summaries: List[str],
                      context: Dict[str, str]) -> str:
        """
        Classify on a single axis with optional context from dependencies.
        Enhanced v2.0 with database-backed rules.
        Extracted per-axis logic from lines 249-273.

        Args:
            axis: Axis configuration
            email_summaries: List of email summaries
            context: Results from previous axes

        Returns:
            Category string from API
        """
        # V2.0: Build prompt with DB rules if available
        prompt = self._build_axis_prompt_with_db(axis, context)
        summaries_text = str(email_summaries)

        return self.api.call_paradigm(prompt, summaries_text)

    def _build_axis_prompt_with_db(self, axis: AxisConfig, context: Dict[str, str]) -> str:
        """
        Build prompt with rules from database (v3.0).
        Rules are now exclusively loaded from database.

        Args:
            axis: Axis configuration
            context: Results from previous axes

        Returns:
            Complete prompt string
        """
        parts = [axis.prompt]

        # v3.0: Always use database for rules
        if self.use_database and self.db:
            try:
                # Use the new reconstruct_full_rules method
                db_rules = self.db.reconstruct_full_rules(axis.name)
                if db_rules and len(db_rules) > 50:
                    parts.append(f"règles à suivre impérativement:\n{db_rules}")
            except Exception as e:
                logger.warning(f"DB rules error: {e}")
                # Fallback to file-based rules only if DB fails
                if axis.rules:
                    parts.append(f"règles à suivre impérativement {axis.rules}")
        elif axis.rules:
            # Legacy: file-based rules when DB not enabled
            parts.append(f"règles à suivre impérativement {axis.rules}")

        # Add context from dependent axes (e.g., projet context for fournisseur)
        for dep in axis.dependencies:
            if dep in context:
                parts.append(f"{dep.capitalize()}: {context[dep]}")

        return ' + '.join(parts)

    def _parse_categories(self, category_string: str) -> List[str]:
        """
        Parse comma-separated categories into list.
        Delegates to centralized utils.parse_categories.

        Args:
            category_string: Comma-separated category string

        Returns:
            List of category strings
        """
        return parse_categories(category_string)

    def _store_classification_in_db(self, conversation_id: str,
                                    emails: List[Dict[str, Any]],
                                    categories: List[str]):
        """
        Store classification results in database (v2.0).

        Args:
            conversation_id: Conversation ID
            emails: List of email data
            categories: Classified categories
        """
        try:
            for email in emails:
                # Check if already stored
                if self.db.email_exists(conversation_id):
                    continue

                # Insert email
                email_id = self.db.insert_email({
                    'conversation_id': conversation_id,
                    'subject': email['subject'],
                    'sender_email': email['sender_email'],
                    'sender_name': email.get('sender_name', ''),
                    'recipients': email['recipients'],
                    'body': email['body'],
                    'received_time': email.get('received_time'),
                    'conversation_topic': email['conversation_topic'],
                    'outlook_categories': ','.join(categories)
                })

                # Link tags
                for category in categories:
                    tag = self.db.get_tag_by_name(category)
                    if tag:
                        self.db.insert_classification(
                            email_id=email_id,
                            tag_id=tag['tag_id'],
                            classified_by='llm',
                            llm_model=self.api.model
                        )

        except Exception as e:
            logger.error(f"Database storage error: {e}")
