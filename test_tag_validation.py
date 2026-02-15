"""
Unit tests for deterministic tag validation against database.
Tests the TagValidator.validate_tags_against_db() method.

Run: python test_tag_validation.py
"""

import sys
import os
import unittest
from unittest.mock import MagicMock

# Add project root to path for direct module import
sys.path.insert(0, os.path.dirname(__file__))


class TestTagValidation(unittest.TestCase):
    """Test deterministic DB validation of tags."""

    def setUp(self):
        """Set up validator with mock DB containing realistic tags."""
        # Mock DB with realistic tag set
        self.valid_tags = {
            # Type axis
            'T_Projet', 'T_Qualite', 'T_Technique', 'T_Anomalie',
            'T_Essais', 'T_Fournisseur', 'T_Communication_Interne',
            'S_Urgent', 'S_Action_Requise', 'S_Pour_Info',
            'S_Classification_incertaine',
            # Projet axis
            'C_AGS', 'C_ADS', 'C_ESA', 'C_CNES',
            'A_YODA', 'A_SICRAL3', 'A_COSMIC',
            'P_Projet_AD', 'P_YODA_CL', 'P_YODA_CE', 'P_AURIGA',
            # Fournisseur
            'F_Safran', 'F_Sodern',
            # Equipement
            'EQT_Camera', 'EQT_Module', 'EQT_Viseur', 'EQT_Objectif',
            'EQ_PFM', 'EQ_STM', 'EQ_FM1', 'EQ_FM2', 'EQ_CAM001',
            'EQ_MV2', 'EQ_MQV', 'EQ_MQV1', 'EQ_MQV2',
            # Processus
            'E_BSI', 'E_BVT', 'E_VIBRATION',
            'PC_DFC', 'PC_ECR', 'TC_Soudure',
            # Qualite
            'Q_NCR', 'J_CDR', 'AN_001', 'NRB_001',
        }

        mock_db = MagicMock()
        mock_db.get_all_active_tag_names.return_value = self.valid_tags
        mock_db.get_all_active_tags_with_axis.return_value = [
            {'tag_name': t, 'axis_name': 'mock', 'prefix': t.split('_')[0] + '_'}
            for t in self.valid_tags
        ]

        mock_config = MagicMock()
        mock_api = MagicMock()

        # Import validator directly, bypassing __init__.py (win32com dependency)
        import importlib.util
        import types

        # Mock the logger dependency
        if 'mail_classifier.logger' not in sys.modules:
            mock_logger_module = types.ModuleType('mail_classifier.logger')
            mock_logger_module.get_logger = lambda name=None: MagicMock()
            sys.modules['mail_classifier.logger'] = mock_logger_module

        # Also ensure mail_classifier package exists in sys.modules
        if 'mail_classifier' not in sys.modules:
            sys.modules['mail_classifier'] = types.ModuleType('mail_classifier')

        spec = importlib.util.spec_from_file_location(
            "mail_classifier.validator",
            os.path.join(os.path.dirname(__file__), "mail_classifier", "validator.py"),
        )
        mod = importlib.util.module_from_spec(spec)
        sys.modules['mail_classifier.validator'] = mod
        spec.loader.exec_module(mod)
        TagValidator = mod.TagValidator
        self.validator = TagValidator(mock_config, mock_api, mock_db)

    def test_valid_tags_pass_through(self):
        """Tags that exist in DB should pass through unchanged."""
        tags = ['T_Projet', 'C_ADS', 'A_YODA', 'P_YODA_CL']
        result = self.validator.validate_tags_against_db(tags)
        self.assertEqual(result['valid_tags'], tags)
        self.assertEqual(result['rejected_tags'], [])
        self.assertEqual(result['corrected_tags'], [])
        self.assertEqual(result['all_clean_tags'], tags)

    def test_double_prefix_C_A_YODA(self):
        """C_A_YODA should be corrected to A_YODA."""
        tags = ['C_A_YODA']
        result = self.validator.validate_tags_against_db(tags)
        self.assertEqual(len(result['corrected_tags']), 1)
        self.assertEqual(result['corrected_tags'][0], ('C_A_YODA', 'A_YODA'))
        self.assertIn('A_YODA', result['all_clean_tags'])

    def test_wrong_prefix_C_DFC(self):
        """C_DFC should be corrected to PC_DFC."""
        tags = ['C_DFC']
        result = self.validator.validate_tags_against_db(tags)
        self.assertEqual(len(result['corrected_tags']), 1)
        self.assertEqual(result['corrected_tags'][0], ('C_DFC', 'PC_DFC'))
        self.assertIn('PC_DFC', result['all_clean_tags'])

    def test_rule_leakage_find(self):
        """EQT_Find_EQ_ should be rejected (rule leakage)."""
        tags = ['EQT_Find_EQ_']
        result = self.validator.validate_tags_against_db(tags)
        self.assertEqual(len(result['rejected_tags']), 1)
        self.assertIn('instruction/rule leakage', result['rejected_tags'][0][1])
        self.assertEqual(result['all_clean_tags'], [])

    def test_rule_leakage_if(self):
        """EQT_If_EQT_inventé should be rejected (rule leakage)."""
        tags = ['EQT_If_EQT_inventé']
        result = self.validator.validate_tags_against_db(tags)
        self.assertEqual(len(result['rejected_tags']), 1)
        self.assertEqual(result['all_clean_tags'], [])

    def test_wrong_prefix_EQT_DFC(self):
        """EQT_DFC should be corrected to PC_DFC."""
        tags = ['EQT_DFC']
        result = self.validator.validate_tags_against_db(tags)
        self.assertEqual(len(result['corrected_tags']), 1)
        self.assertEqual(result['corrected_tags'][0], ('EQT_DFC', 'PC_DFC'))

    def test_wrong_prefix_EQT_ECR(self):
        """EQT_ECR should be corrected to PC_ECR."""
        tags = ['EQT_ECR']
        result = self.validator.validate_tags_against_db(tags)
        self.assertEqual(len(result['corrected_tags']), 1)
        self.assertEqual(result['corrected_tags'][0], ('EQT_ECR', 'PC_ECR'))

    def test_completely_invented_tag(self):
        """A completely invented tag should be rejected."""
        tags = ['X_NonExistent']
        result = self.validator.validate_tags_against_db(tags)
        self.assertEqual(len(result['rejected_tags']), 1)
        self.assertEqual(result['all_clean_tags'], [])

    def test_mixed_valid_and_invalid(self):
        """Mix of valid, correctable, and invalid tags."""
        tags = [
            'T_Projet',          # valid
            'C_A_YODA',          # correctable -> A_YODA
            'EQT_Find_EQ_',      # rejected (leakage)
            'S_Urgent',          # valid
            'C_DFC',             # correctable -> PC_DFC
        ]
        result = self.validator.validate_tags_against_db(tags)
        self.assertEqual(len(result['valid_tags']), 2)  # T_Projet, S_Urgent
        self.assertEqual(len(result['corrected_tags']), 2)  # A_YODA, PC_DFC
        self.assertEqual(len(result['rejected_tags']), 1)  # EQT_Find_EQ_
        self.assertIn('T_Projet', result['all_clean_tags'])
        self.assertIn('S_Urgent', result['all_clean_tags'])
        self.assertIn('A_YODA', result['all_clean_tags'])
        self.assertIn('PC_DFC', result['all_clean_tags'])

    def test_deduplication(self):
        """Corrected tags should not create duplicates."""
        tags = ['A_YODA', 'C_A_YODA']  # both resolve to A_YODA
        result = self.validator.validate_tags_against_db(tags)
        self.assertEqual(result['all_clean_tags'].count('A_YODA'), 1)

    def test_empty_tags(self):
        """Empty tag list should return empty results."""
        result = self.validator.validate_tags_against_db([])
        self.assertEqual(result['all_clean_tags'], [])

    def test_whitespace_handling(self):
        """Tags with whitespace should be stripped."""
        tags = ['  T_Projet  ', ' S_Urgent']
        result = self.validator.validate_tags_against_db(tags)
        self.assertEqual(len(result['valid_tags']), 2)

    def test_case_insensitive_match(self):
        """Case-insensitive matching should find the correct tag."""
        tags = ['t_projet']  # lowercase
        result = self.validator.validate_tags_against_db(tags)
        self.assertEqual(len(result['corrected_tags']), 1)
        self.assertEqual(result['corrected_tags'][0][1], 'T_Projet')

    def test_extract_prefix_multichar(self):
        """Multi-character prefixes like EQT_, NRB_ should be extracted correctly."""
        prefix, remainder = self.validator._extract_prefix('EQT_Camera')
        self.assertEqual(prefix, 'EQT_')
        self.assertEqual(remainder, 'Camera')

        prefix, remainder = self.validator._extract_prefix('NRB_001')
        self.assertEqual(prefix, 'NRB_')
        self.assertEqual(remainder, '001')

        prefix, remainder = self.validator._extract_prefix('T_Projet')
        self.assertEqual(prefix, 'T_')
        self.assertEqual(remainder, 'Projet')

    def test_extract_prefix_unknown(self):
        """Unknown prefixes should return None."""
        prefix, remainder = self.validator._extract_prefix('X_Unknown')
        self.assertIsNone(prefix)
        self.assertEqual(remainder, 'X_Unknown')


if __name__ == '__main__':
    # Run tests
    unittest.main(verbosity=2)
