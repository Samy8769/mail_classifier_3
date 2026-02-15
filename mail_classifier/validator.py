"""
LLM-based validation of classification tags.
Ensures output quality and conformance to rules.
"""

import re
from typing import List, Dict, Any


class TagValidator:
    """
    Post-classification validation layer.
    Verifies tag conformity and format using LLM.
    """

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
        self.validation_prompt_template = self._get_validation_prompt_template()

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

            return result

        except Exception as e:
            print(f"⚠ Validation error: {e}")
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
            if '_' in tag:
                prefix = tag.split('_')[0] + '_'
                # Map prefix to axis
                axis_map = {
                    'T_': 'type',
                    'S_': 'type',
                    'P_': 'projet',
                    'A_': 'projet',
                    'C_': 'projet',
                    'F_': 'fournisseur',
                    'E_': 'equipement',
                    'Proc_': 'processus'
                }
                axis = axis_map.get(prefix)
                if axis:
                    axes_detected.add(axis)

        # Get allowed tags from database for detected axes
        allowed_tags = {}
        multiplicity_rules = {}

        for axis in axes_detected:
            db_tags = self.db.get_tags_by_axis(axis)
            allowed_tags[axis] = [t['tag_name'] for t in db_tags]

            # Get multiplicity from first tag metadata (if available)
            if db_tags and db_tags[0]['tag_metadata']:
                try:
                    metadata = db_tags[0]['tag_metadata']
                    if isinstance(metadata, dict) and 'multiplicity' in metadata:
                        multiplicity_rules[axis] = metadata['multiplicity']
                    else:
                        multiplicity_rules[axis] = '0..*'  # Default: any number
                except:
                    multiplicity_rules[axis] = '0..*'
            else:
                multiplicity_rules[axis] = '0..*'

        # Format as strings
        allowed_tags_str = '\n'.join([
            f"  {axis}: {', '.join(tags[:10])}{'...' if len(tags) > 10 else ''}"
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
                # No corrections found, use original
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

    def validate_and_correct(self, email_id: int,
                            email_summaries: str,
                            proposed_tags: List[str]) -> List[str]:
        """
        Validate tags and return corrected version.
        Integrates into classification pipeline.

        Args:
            email_id: Email being classified
            email_summaries: Email summaries
            proposed_tags: Proposed tags from classifier

        Returns:
            Corrected/validated tags
        """
        print(f"  🔍 Validating {len(proposed_tags)} tags...", end='')

        # Skip if no tags to validate
        if not proposed_tags:
            print(" (no tags)")
            return proposed_tags

        validation_result = self.validate_classification(email_summaries, proposed_tags)

        if not validation_result['valid']:
            print(f" ⚠ ISSUES FOUND")
            print(f"    Issues: {', '.join(validation_result['issues'])}")
            print(f"    Corrected: {validation_result['corrected_tags']}")
            return validation_result['corrected_tags']
        else:
            print(f" ✓ VALID")
            return proposed_tags

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
            if not re.match(r'^[A-Z]+_[A-Za-z0-9_-]+$', tag):
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
