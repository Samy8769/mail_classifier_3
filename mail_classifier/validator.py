"""
LLM-based and deterministic validation of classification tags.
Ensures output quality and conformance to rules.

v3.2: Added deterministic DB validation layer that filters tags
against the actual database before optional LLM validation.
"""

import re
from typing import List, Dict, Any, Optional, Set, Tuple
from .logger import get_logger

logger = get_logger('validator')


class TagValidator:
    """
    Post-classification validation layer.
    Two-stage approach:
      1. Deterministic DB validation (hard filter against known tags)
      2. Optional LLM validation (semantic/contextual check)
    """

    # Known prefixes and their axes
    PREFIX_TO_AXIS = {
        'T_': 'type',
        'S_': 'type',
        'P_': 'projet',
        'A_': 'projet',
        'C_': 'projet',
        'F_': 'fournisseur',
        'EQT_': 'equipement',
        'EQ_': 'equipement',
        'E_': 'processus',
        'TC_': 'processus',
        'PC_': 'processus',
        'Q_': 'qualite',
        'J_': 'qualite',
        'AN_': 'qualite',
        'NRB_': 'qualite',
    }

    # All known prefixes sorted by length descending (longest match first)
    KNOWN_PREFIXES = sorted(PREFIX_TO_AXIS.keys(), key=len, reverse=True)

    def __init__(self, config, api_client, db):
        """
        Args:
            config: Configuration object
            api_client: API client for LLM calls
            db: Database manager
        """
        self.config = config
        self.api = api_client
        self.db = db
        self._valid_tags_cache = None
        self._all_tags_with_info_cache = None
        self.validation_prompt_template = self._get_validation_prompt_template()

    def _get_valid_tags(self) -> Set[str]:
        """Get cached set of all valid tag names from DB."""
        if self._valid_tags_cache is None:
            self._valid_tags_cache = self.db.get_all_active_tag_names()
        return self._valid_tags_cache

    def _get_all_tags_with_info(self) -> List[Dict]:
        """Get cached list of all tags with axis/prefix info."""
        if self._all_tags_with_info_cache is None:
            self._all_tags_with_info_cache = self.db.get_all_active_tags_with_axis()
        return self._all_tags_with_info_cache

    def invalidate_cache(self):
        """Invalidate tag cache (call after DB changes)."""
        self._valid_tags_cache = None
        self._all_tags_with_info_cache = None

    # ==================== Stage 1: Deterministic DB Validation ====================

    def validate_tags_against_db(self, proposed_tags: List[str]) -> Dict[str, Any]:
        """
        Deterministic validation: check every tag exists in the database.
        For invalid tags, attempt fuzzy correction. Remove unfixable tags.

        Args:
            proposed_tags: Tags proposed by the classification pipeline

        Returns:
            Dictionary with:
            - valid_tags: List[str] - tags that passed validation
            - rejected_tags: List[Tuple[str, str]] - (tag, reason) pairs
            - corrected_tags: List[Tuple[str, str]] - (original, corrected) pairs
            - all_clean_tags: List[str] - final clean list (valid + corrected)
        """
        valid_tags_db = self._get_valid_tags()

        valid_tags = []
        rejected_tags = []
        corrected_tags = []

        for tag in proposed_tags:
            tag = tag.strip()
            if not tag:
                continue

            # Step 1: Exact match in DB
            if tag in valid_tags_db:
                valid_tags.append(tag)
                continue

            # Step 2: Try to correct the tag
            corrected = self._try_correct_tag(tag, valid_tags_db)
            if corrected:
                corrected_tags.append((tag, corrected))
                continue

            # Step 3: Tag is invalid and unfixable
            reason = self._diagnose_rejection(tag, valid_tags_db)
            rejected_tags.append((tag, reason))

        # Build final clean list (valid + corrected, deduplicated)
        all_clean = list(valid_tags)
        for _, corrected_tag in corrected_tags:
            if corrected_tag not in all_clean:
                all_clean.append(corrected_tag)

        return {
            'valid_tags': valid_tags,
            'rejected_tags': rejected_tags,
            'corrected_tags': corrected_tags,
            'all_clean_tags': all_clean,
        }

    def _extract_prefix(self, tag: str) -> Tuple[Optional[str], str]:
        """
        Extract the prefix from a tag using known prefixes.
        Handles multi-character prefixes like EQT_, NRB_, etc.

        Returns:
            (prefix, remainder) or (None, tag) if no known prefix found
        """
        for prefix in self.KNOWN_PREFIXES:
            if tag.startswith(prefix):
                return prefix, tag[len(prefix):]
        return None, tag

    def _try_correct_tag(self, tag: str, valid_tags_db: Set[str]) -> Optional[str]:
        """
        Attempt to correct an invalid tag to a valid one.
        Handles common LLM errors:
          - Double prefix: C_A_YODA → A_YODA
          - Wrong prefix: C_DFC → PC_DFC
          - Rule leakage: EQT_Find_EQ_ → rejected
          - Instruction leakage: EQT_If_EQT_inventé → rejected

        Args:
            tag: Invalid tag to correct
            valid_tags_db: Set of valid tags

        Returns:
            Corrected tag name or None if unfixable
        """
        # Reject obvious instruction/rule leakage
        leakage_patterns = [
            r'(?i)find', r'(?i)if_', r'(?i)invent',
            r'(?i)example', r'(?i)exemple', r'(?i)suggest',
            r'(?i)cherch', r'(?i)trouv',
        ]
        for pattern in leakage_patterns:
            if re.search(pattern, tag):
                return None

        # Strategy 1: The tag name (without its prefix) may be a valid tag
        # with a different prefix. e.g., C_A_YODA → A_YODA exists in DB
        prefix, remainder = self._extract_prefix(tag)
        if prefix and remainder:
            # Check if the remainder itself is a valid tag (double prefix case)
            if remainder in valid_tags_db:
                return remainder

            # Check if remainder starts with another known prefix
            inner_prefix, inner_remainder = self._extract_prefix(remainder)
            if inner_prefix and f"{inner_prefix}{inner_remainder}" in valid_tags_db:
                return f"{inner_prefix}{inner_remainder}"

        # Strategy 2: Try all known prefixes with the base name
        # Extract the base name (everything after all prefixes)
        base_name = tag
        for pfx in self.KNOWN_PREFIXES:
            if base_name.startswith(pfx):
                base_name = base_name[len(pfx):]
                break

        if base_name:
            for try_prefix in self.KNOWN_PREFIXES:
                candidate = f"{try_prefix}{base_name}"
                if candidate in valid_tags_db:
                    return candidate

        # Strategy 3: Case-insensitive match
        tag_lower = tag.lower()
        for valid_tag in valid_tags_db:
            if valid_tag.lower() == tag_lower:
                return valid_tag

        # Strategy 4: Substring match - tag name contained in a valid tag
        # Only for sufficiently long base names to avoid false matches
        if base_name and len(base_name) >= 3:
            for valid_tag in valid_tags_db:
                valid_prefix, valid_remainder = self._extract_prefix(valid_tag)
                if valid_remainder and valid_remainder.lower() == base_name.lower():
                    return valid_tag

        return None

    def _diagnose_rejection(self, tag: str, valid_tags_db: Set[str]) -> str:
        """
        Provide a diagnostic reason for why a tag was rejected.

        Args:
            tag: The rejected tag
            valid_tags_db: Set of valid tags

        Returns:
            Human-readable reason string
        """
        # Check for instruction leakage
        if re.search(r'(?i)(find|if_|invent|example|suggest|cherch|trouv)', tag):
            return "instruction/rule leakage in tag"

        # Check prefix
        prefix, remainder = self._extract_prefix(tag)
        if prefix is None:
            return f"unknown prefix format"

        # Check if prefix exists in DB but name doesn't
        axis = self.PREFIX_TO_AXIS.get(prefix, 'unknown')
        db_tags_for_axis = [t for t in valid_tags_db if t.startswith(prefix)]
        if db_tags_for_axis:
            return f"'{remainder}' not found in {prefix} tags (axis: {axis})"
        else:
            return f"no {prefix} tags found in database"

    # ==================== Stage 2: LLM Validation ====================

    def _get_validation_prompt_template(self) -> str:
        """Get validation prompt template."""
        return """Tu es un assistant de validation. Ta tâche est de vérifier qu'une liste de tags de classification est conforme aux règles suivantes :

1. La sortie doit être UNIQUEMENT une liste de tags séparés par des virgules
2. Chaque tag doit suivre le format : PREFIX_Nom (ex: T_Projet, P_YODA_CE, F_Safran)
3. Pas d'explications, pas de texte additionnel, pas de markdown
4. Les tags doivent exister dans la liste des tags autorisés fournie
5. Les règles de multiplicité doivent être respectées

## Email résumé :
{email_summaries}

## Tags proposés :
{proposed_tags}

## Tags autorisés par axe :
{allowed_tags}

## Règles de multiplicité :
{multiplicity_rules}

## Ta réponse :
Si les tags sont VALIDES, réponds : "VALID: [tag1, tag2, ...]"
Si les tags sont INVALIDES, réponds : "INVALID: [raison]" suivi de la liste corrigée "[tag1_corrigé, tag2_corrigé, ...]"
"""

    def validate_classification(self, email_summaries: str,
                                proposed_tags: List[str]) -> Dict[str, Any]:
        """
        Validate proposed tags via LLM call.

        Args:
            email_summaries: Original email summaries
            proposed_tags: Tags proposed by classifier

        Returns:
            Dictionary with:
            - valid: bool
            - corrected_tags: List[str] (if corrections made)
            - issues: List[str] (validation issues found)
            - explanation: str
        """
        # Build validation context
        validation_context = self._build_validation_context(proposed_tags)

        # Prepare validation prompt
        full_prompt = self.validation_prompt_template.format(
            email_summaries=email_summaries,
            proposed_tags=', '.join(proposed_tags),
            allowed_tags=validation_context['allowed_tags_str'],
            multiplicity_rules=validation_context['multiplicity_rules_str']
        )

        try:
            # Call LLM
            response = self.api.call_paradigm(full_prompt, "")

            # Parse validation response
            result = self._parse_validation_response(response, proposed_tags)

            # Post-filter LLM response: ensure corrected_tags also exist in DB
            valid_tags_db = self._get_valid_tags()
            result['corrected_tags'] = [
                t for t in result['corrected_tags'] if t in valid_tags_db
            ]

            return result

        except Exception as e:
            logger.warning(f"Validation LLM error: {e}")
            # Fallback: assume valid
            return {
                'valid': True,
                'corrected_tags': proposed_tags,
                'issues': [f'Validation failed: {e}'],
                'explanation': 'Validation skipped due to error'
            }

    def _build_validation_context(self, proposed_tags: List[str]) -> Dict:
        """
        Build context of allowed tags and rules for validation.

        Args:
            proposed_tags: List of proposed tags

        Returns:
            Dictionary with validation context
        """
        # Detect axes from tag prefixes
        axes_detected = set()
        for tag in proposed_tags:
            prefix, _ = self._extract_prefix(tag)
            if prefix:
                axis = self.PREFIX_TO_AXIS.get(prefix)
                if axis:
                    axes_detected.add(axis)

        # Get allowed tags from database for detected axes
        allowed_tags = {}
        multiplicity_rules = {}

        for axis in axes_detected:
            db_tags = self.db.get_tags_by_axis(axis)
            # Show ALL tags, not truncated
            allowed_tags[axis] = [t['tag_name'] for t in db_tags]

            # Get multiplicity from first tag metadata (if available)
            if db_tags and db_tags[0]['tag_metadata']:
                try:
                    metadata = db_tags[0]['tag_metadata']
                    if isinstance(metadata, dict) and 'multiplicity' in metadata:
                        multiplicity_rules[axis] = metadata['multiplicity']
                    else:
                        multiplicity_rules[axis] = '0..*'
                except Exception:
                    multiplicity_rules[axis] = '0..*'
            else:
                multiplicity_rules[axis] = '0..*'

        # Format as strings - show ALL tags
        allowed_tags_str = '\n'.join([
            f"  {axis}: {', '.join(tags)}"
            for axis, tags in allowed_tags.items()
        ])

        multiplicity_rules_str = '\n'.join([
            f"  {axis}: {mult}"
            for axis, mult in multiplicity_rules.items()
        ])

        return {
            'allowed_tags': allowed_tags,
            'multiplicity_rules': multiplicity_rules,
            'allowed_tags_str': allowed_tags_str,
            'multiplicity_rules_str': multiplicity_rules_str
        }

    def _parse_validation_response(self, response: str,
                                   original_tags: List[str]) -> Dict:
        """
        Parse LLM validation response.

        Args:
            response: LLM response text
            original_tags: Original tag list

        Returns:
            Validation result dictionary
        """
        response = response.strip()

        # Check if valid
        if response.upper().startswith("VALID"):
            # Extract tags from response (if present)
            match = re.search(r'\[(.*?)\]', response)
            if match:
                validated_tags_str = match.group(1)
                validated_tags = [
                    t.strip().strip('"\'')
                    for t in validated_tags_str.split(',')
                    if t.strip()
                ]
            else:
                validated_tags = original_tags

            return {
                'valid': True,
                'corrected_tags': validated_tags,
                'issues': [],
                'explanation': response
            }

        elif response.upper().startswith("INVALID"):
            # Extract issues and corrected tags
            lines = response.split('\n')
            issues = [lines[0].replace("INVALID:", "").strip()]

            # Look for corrected tags in square brackets
            corrected_tags = []
            for line in lines:
                match = re.search(r'\[(.*?)\]', line)
                if match:
                    tags_str = match.group(1)
                    corrected_tags = [
                        t.strip().strip('"\'')
                        for t in tags_str.split(',')
                        if t.strip()
                    ]
                    break

            if not corrected_tags:
                corrected_tags = original_tags

            return {
                'valid': False,
                'corrected_tags': corrected_tags,
                'issues': issues,
                'explanation': response
            }

        else:
            # Unclear response, assume valid
            return {
                'valid': True,
                'corrected_tags': original_tags,
                'issues': ['Unclear validation response'],
                'explanation': response
            }

    # ==================== Combined Pipeline ====================

    def validate_and_correct(self, email_id,
                            email_summaries: str,
                            proposed_tags: List[str]) -> List[str]:
        """
        Full validation pipeline:
        1. Deterministic DB validation (always runs)
        2. Optional LLM validation (if enabled)

        Args:
            email_id: Email being classified
            email_summaries: Email summaries
            proposed_tags: Proposed tags from classifier

        Returns:
            Corrected/validated tags
        """
        if not proposed_tags:
            logger.info("  No tags to validate")
            return proposed_tags

        # ---- Stage 1: Deterministic DB validation ----
        logger.info(f"  [Validation] Stage 1: checking {len(proposed_tags)} tags against DB...")
        db_result = self.validate_tags_against_db(proposed_tags)

        # Log corrections
        for original, corrected in db_result['corrected_tags']:
            logger.info(f"    CORRECTED: '{original}' -> '{corrected}'")

        # Log rejections
        for tag, reason in db_result['rejected_tags']:
            logger.warning(f"    REJECTED: '{tag}' ({reason})")

        clean_tags = db_result['all_clean_tags']

        if db_result['rejected_tags'] or db_result['corrected_tags']:
            n_ok = len(db_result['valid_tags'])
            n_fix = len(db_result['corrected_tags'])
            n_rej = len(db_result['rejected_tags'])
            logger.info(f"  [Validation] Stage 1 result: {n_ok} valid, {n_fix} corrected, {n_rej} rejected")
        else:
            logger.info(f"  [Validation] Stage 1: all {len(clean_tags)} tags valid")

        # ---- Stage 2: LLM validation (optional, on clean tags) ----
        use_llm_validation = self._get_config_flag('validation', 'llm_enabled', False)
        if use_llm_validation and clean_tags:
            logger.info(f"  [Validation] Stage 2: LLM validation on {len(clean_tags)} tags...")
            llm_result = self.validate_classification(email_summaries, clean_tags)

            if not llm_result['valid']:
                logger.info(f"    LLM issues: {', '.join(llm_result['issues'])}")
                clean_tags = llm_result['corrected_tags']
                logger.info(f"    LLM corrected to: {clean_tags}")
            else:
                logger.info(f"  [Validation] Stage 2: LLM confirms valid")

        return clean_tags

    def _get_config_flag(self, section: str, key: str, default=None):
        """Safely get a config flag value."""
        try:
            if hasattr(self.config, section):
                section_data = getattr(self.config, section)
                if isinstance(section_data, dict):
                    return section_data.get(key, default)
            return default
        except Exception:
            return default

    # ==================== Quick Format Validation ====================

    def quick_validate_format(self, tags: List[str]) -> Dict[str, Any]:
        """
        Quick format validation without LLM call.
        Checks basic format rules.

        Args:
            tags: List of tags to validate

        Returns:
            Dictionary with validation result
        """
        issues = []
        valid_tags = []

        for tag in tags:
            # Check format: PREFIX_Name
            if '_' not in tag:
                issues.append(f"Tag '{tag}' missing underscore separator")
                continue

            # Check prefix is uppercase
            prefix = tag.split('_')[0]
            if not prefix.isupper():
                issues.append(f"Tag '{tag}' prefix should be uppercase")
                continue

            # Check no special characters (except underscore, hyphen)
            if not re.match(r'^[A-Z]+_[A-Za-z0-9_² -]+$', tag):
                issues.append(f"Tag '{tag}' contains invalid characters")
                continue

            valid_tags.append(tag)

        return {
            'valid': len(issues) == 0,
            'valid_tags': valid_tags,
            'issues': issues
        }


# Convenience function
def create_validator(config, api_client, db) -> TagValidator:
    """
    Create TagValidator instance.

    Args:
        config: Configuration object
        api_client: API client instance
        db: DatabaseManager instance

    Returns:
        TagValidator instance
    """
    return TagValidator(config, api_client, db)
