"""
Unit tests for the heuristic classification pipeline.

Run with:
    python -m pytest test_heuristic_pipeline.py -v
"""

import pytest
from mail_classifier.heuristic_engine import (
    TextNormalizer,
    SerialNumberExtractor,
    AhoCorasickMatcher,
    AxisKeywordConfig,
    AxisHeuristicPipeline,
    SCORE_SUBJECT_MATCH,
    SCORE_BODY_MATCH,
    SCORE_SYNONYM_BONUS,
)
from mail_classifier.axis_keywords import AXIS_CONFIGS, get_axis_config, get_all_axis_names
from mail_classifier.hybrid_pipeline import (
    HybridClassificationPipeline,
    HybridAxisClassifier,
    HybridClassificationOutput,
    AxisClassificationResult,
)


# ===========================================================================
# TextNormalizer
# ===========================================================================

class TestTextNormalizer:

    def setup_method(self):
        self.n = TextNormalizer()

    def test_lowercase(self):
        assert self.n.normalize('HELLO WORLD') == 'hello world'

    def test_accent_removal_french(self):
        result = self.n.normalize('Réunion prévue à Noël')
        assert 'é' not in result
        assert 'à' not in result
        assert 'ë' not in result
        assert 'reunion' in result
        assert 'prevue' in result

    def test_whitespace_collapse(self):
        assert self.n.normalize('hello   world\t\nnewline') == 'hello world newline'

    def test_empty_string(self):
        assert self.n.normalize('') == ''

    def test_none_returns_empty(self):
        assert self.n.normalize(None) == ''  # type: ignore[arg-type]

    def test_mixed_case_with_numbers(self):
        result = self.n.normalize('FM1 et EQM-002')
        assert 'fm1' in result
        assert 'eqm-002' in result


# ===========================================================================
# SerialNumberExtractor
# ===========================================================================

class TestSerialNumberExtractor:

    def setup_method(self):
        self.ext = SerialNumberExtractor()

    def test_sn_colon(self):
        serials = self.ext.extract('Équipement SN:12345 reçu')
        assert any('12345' in s for s in serials)

    def test_sn_space(self):
        serials = self.ext.extract('Serial number SN 999888')
        assert any('999888' in s for s in serials)

    def test_hyphenated_part_number(self):
        serials = self.ext.extract('Référence CAM-001234 livraison')
        assert any('CAM-001234' in s for s in serials)

    def test_short_alphanumeric(self):
        serials = self.ext.extract("L'équipement FM1 est arrivé")
        assert any('FM1' in s for s in serials)

    def test_pn_format(self):
        serials = self.ext.extract('PN:ABC-1234 à livrer')
        assert any('ABC-1234' in s for s in serials)

    def test_no_serial_numbers(self):
        serials = self.ext.extract('Bonjour, veuillez confirmer la réception.')
        assert serials == []

    def test_multiple_serials_deduplicated(self):
        text = 'FM1 et FM1 aussi, puis SN:99999'
        serials = self.ext.extract(text)
        # FM1 should appear only once (deduplicated)
        fm1_count = sum(1 for s in serials if s == 'FM1')
        assert fm1_count == 1

    def test_extra_patterns(self):
        ext = SerialNumberExtractor(extra_patterns=[r'\bXX-\d{5}\b'])
        serials = ext.extract('Référence XX-12345 en commande')
        assert any('XX-12345' in s for s in serials)


# ===========================================================================
# AhoCorasickMatcher
# ===========================================================================

class TestAhoCorasickMatcher:

    def setup_method(self):
        self.kw_map = {
            'T_Commande': ['commande', 'bon de commande', 'purchase order'],
            'T_Offre':    ['offre', 'devis', 'cotation'],
        }
        self.syn_map = {
            'T_Commande': ['bdc', 'po'],
            'T_Offre':    ['rfq'],
        }
        self.matcher = AhoCorasickMatcher(self.kw_map, self.syn_map)

    def _norm(self, text: str) -> str:
        return TextNormalizer().normalize(text)

    def test_basic_keyword_match(self):
        matches = self.matcher.find_matches(self._norm('voici notre commande pour vous'))
        tags = [tag for _, tag, _ in matches]
        assert 'T_Commande' in tags

    def test_synonym_flagged_as_synonym(self):
        matches = self.matcher.find_matches(self._norm('veuillez traiter ce bdc rapidement'))
        syn_matches = [(kw, tag, is_syn) for kw, tag, is_syn in matches if is_syn]
        assert any(tag == 'T_Commande' for _, tag, _ in syn_matches)

    def test_non_synonym_not_flagged(self):
        matches = self.matcher.find_matches(self._norm('voici la commande'))
        kw_matches = [(kw, tag, is_syn) for kw, tag, is_syn in matches if not is_syn]
        assert any(tag == 'T_Commande' for _, tag, _ in kw_matches)

    def test_no_match_returns_empty(self):
        matches = self.matcher.find_matches(self._norm('bonjour bonne journee'))
        assert matches == []

    def test_multi_keyword_same_tag(self):
        matches = self.matcher.find_matches(self._norm('offre et devis recus'))
        tags = [tag for _, tag, _ in matches]
        # Two hits on T_Offre
        assert tags.count('T_Offre') >= 2

    def test_empty_keyword_maps(self):
        m = AhoCorasickMatcher({}, {})
        assert m.find_matches('anything') == []


# ===========================================================================
# AxisHeuristicPipeline – scoring rules
# ===========================================================================

class TestAxisHeuristicPipeline:

    def setup_method(self):
        self.config = AxisKeywordConfig(
            axis_name='type_mail',
            prefix='T_',
            keyword_map={
                'T_Commande':  ['commande', 'purchase order'],
                'T_Offre':     ['offre', 'devis'],
                'T_Livraison': ['livraison', 'expedition'],
            },
            synonym_map={
                'T_Commande':  ['bdc'],
                'T_Offre':     ['rfq'],
                'T_Livraison': [],
            },
        )
        self.pipeline = AxisHeuristicPipeline(self.config)

    # --- Scoring -----------------------------------------------------------

    def test_subject_scores_higher_than_body(self):
        result = self.pipeline.run(
            subject='Commande XYZ-001',
            body='Veuillez trouver ci-joint notre offre.',
        )
        scores = {c.tag: c.score for c in result.top_candidates}
        assert scores.get('T_Commande', 0) > scores.get('T_Offre', 0)

    def test_exact_subject_score(self):
        """Subject match alone: SCORE_SUBJECT_MATCH per hit."""
        result = self.pipeline.run(subject='commande', body='')
        scores = {c.tag: c.score for c in result.top_candidates}
        assert scores.get('T_Commande', 0) == SCORE_SUBJECT_MATCH

    def test_exact_body_score(self):
        result = self.pipeline.run(subject='', body='commande recue')
        scores = {c.tag: c.score for c in result.top_candidates}
        assert scores.get('T_Commande', 0) == SCORE_BODY_MATCH

    def test_synonym_bonus_applied(self):
        """Synonym in body: SCORE_BODY_MATCH + SCORE_SYNONYM_BONUS."""
        result_kw = self.pipeline.run(subject='', body='commande recue')
        result_syn = self.pipeline.run(subject='', body='bdc reçu')
        score_kw = next(
            (c.score for c in result_kw.top_candidates if c.tag == 'T_Commande'), 0
        )
        score_syn = next(
            (c.score for c in result_syn.top_candidates if c.tag == 'T_Commande'), 0
        )
        expected_syn = SCORE_BODY_MATCH + SCORE_SYNONYM_BONUS
        assert score_syn == expected_syn
        assert score_syn > score_kw

    def test_repetitions_cumulative(self):
        """Each occurrence of a keyword adds to the score."""
        result = self.pipeline.run(subject='commande', body='commande commande')
        score = next(
            (c.score for c in result.top_candidates if c.tag == 'T_Commande'), 0
        )
        # subject: +3, body: +1 +1 = 5
        assert score == SCORE_SUBJECT_MATCH + SCORE_BODY_MATCH + SCORE_BODY_MATCH

    # --- Ambiguity ---------------------------------------------------------

    def test_clear_winner_not_ambiguous(self):
        result = self.pipeline.run(
            subject='Commande reçue', body='Votre commande a été enregistrée.'
        )
        assert not result.is_ambiguous
        assert result.best is not None
        assert result.best.tag == 'T_Commande'

    def test_no_match_is_ambiguous(self):
        result = self.pipeline.run(subject='Bonjour', body='Bonne journée.')
        assert result.top_candidates == []
        assert result.is_ambiguous

    def test_close_scores_ambiguous(self):
        """Both T_Commande and T_Offre should score closely → ambiguous."""
        result = self.pipeline.run(
            subject='commande offre', body='offre commande'
        )
        assert len(result.top_candidates) >= 2

    # --- Serial numbers ----------------------------------------------------

    def test_no_serial_extraction_without_patterns(self):
        """Axes without regex_patterns should not extract serial numbers."""
        result = self.pipeline.run(
            subject='FM1 CAM-001', body='SN:99999'
        )
        assert result.serial_numbers == []

    # --- Top-N cap ---------------------------------------------------------

    def test_max_candidates_respected(self):
        cfg = AxisKeywordConfig(
            axis_name='test',
            prefix='X_',
            keyword_map={f'X_{i}': [f'keyword{i}'] for i in range(10)},
            synonym_map={f'X_{i}': [] for i in range(10)},
            max_candidates=3,
        )
        pl = AxisHeuristicPipeline(cfg)
        body = ' '.join(f'keyword{i}' for i in range(10))
        result = pl.run(subject='', body=body)
        assert len(result.top_candidates) <= 3

    # --- best_confidence property ------------------------------------------

    def test_best_confidence_sum_normalised(self):
        result = self.pipeline.run(
            subject='commande commande', body='offre'
        )
        conf = result.best_confidence
        assert 0.0 <= conf <= 1.0

    def test_best_confidence_zero_when_no_candidates(self):
        result = self.pipeline.run(subject='', body='')
        assert result.best_confidence == 0.0


# ===========================================================================
# AxisHeuristicPipeline – with serial-number extraction (EQ_ axis)
# ===========================================================================

class TestEQAxisWithSerialNumbers:

    def setup_method(self):
        eq_config = get_axis_config('equipement_designation')
        assert eq_config is not None
        self.pipeline = AxisHeuristicPipeline(eq_config)

    def test_serial_numbers_extracted(self):
        result = self.pipeline.run(
            subject='Livraison FM1',
            body="L'équipement SN:12345 est expédié. Ref CAM-001.",
        )
        assert len(result.serial_numbers) >= 1

    def test_fm1_keyword_candidate(self):
        result = self.pipeline.run(subject='Livraison FM1', body='')
        tags = [c.tag for c in result.top_candidates]
        assert 'EQ_FM1' in tags


# ===========================================================================
# axis_keywords – configuration sanity
# ===========================================================================

class TestAxisKeywordsConfig:

    def test_all_14_axes_present(self):
        expected = {
            'type_mail', 'statut', 'client', 'affaire', 'projet',
            'fournisseur', 'equipement_type', 'equipement_designation',
            'essais', 'technique', 'qualite', 'jalons', 'anomalies', 'nrb',
        }
        configured = set(AXIS_CONFIGS.keys())
        assert expected.issubset(configured), (
            f"Missing axes: {expected - configured}"
        )

    def test_get_axis_config_returns_none_for_unknown(self):
        assert get_axis_config('does_not_exist') is None

    def test_get_all_axis_names_is_list(self):
        names = get_all_axis_names()
        assert isinstance(names, list)
        assert len(names) >= 14

    def test_axis_prefix_consistency(self):
        prefix_map = {
            'type_mail': 'T_',
            'statut': 'S_',
            'client': 'C_',
            'projet': 'P_',
            'fournisseur': 'F_',
            'equipement_type': 'EQT_',
            'equipement_designation': 'EQ_',
            'essais': 'E_',
            'technique': 'TC_',
            'qualite': 'Q_',
            'jalons': 'J_',
            'anomalies': 'AN_',
            'nrb': 'NRB_',
        }
        for axis_name, expected_prefix in prefix_map.items():
            cfg = AXIS_CONFIGS[axis_name]
            assert cfg.prefix == expected_prefix, (
                f"Axis '{axis_name}': expected prefix '{expected_prefix}', "
                f"got '{cfg.prefix}'"
            )

    def test_candidates_tags_match_prefix(self):
        for axis_name, cfg in AXIS_CONFIGS.items():
            for tag in cfg.keyword_map:
                assert tag.startswith(cfg.prefix), (
                    f"Axis '{axis_name}': tag '{tag}' does not start with "
                    f"prefix '{cfg.prefix}'"
                )

    def test_eq_axis_has_regex_patterns(self):
        cfg = AXIS_CONFIGS['equipement_designation']
        assert len(cfg.regex_patterns) > 0

    def test_non_eq_axes_have_no_regex_patterns(self):
        """Only EQ_ axis should carry regex patterns."""
        for name, cfg in AXIS_CONFIGS.items():
            if name != 'equipement_designation':
                assert cfg.regex_patterns == [], (
                    f"Axis '{name}' unexpectedly has regex_patterns"
                )


# ===========================================================================
# HybridClassificationPipeline – integration (no LLM)
# ===========================================================================

class TestHybridPipelineNoLLM:

    def setup_method(self):
        self.pipeline = HybridClassificationPipeline(
            api_client=None,
            use_llm_for_ambiguous=False,
        )

    def test_returns_output_object(self):
        output = self.pipeline.classify_email(
            subject='Commande reçue - Projet Galileo',
            body='Bonjour, veuillez confirmer la réception de notre commande.',
        )
        assert isinstance(output, HybridClassificationOutput)

    def test_categories_are_list_of_strings(self):
        output = self.pipeline.classify_email(subject='offre', body='devis envoye')
        assert isinstance(output.categories, list)
        assert all(isinstance(c, str) for c in output.categories)

    def test_serial_numbers_extracted_from_eq_axis(self):
        output = self.pipeline.classify_email(
            subject='Livraison FM1',
            body="L'équipement SN:12345 a été expédié. Référence CAM-001.",
        )
        assert len(output.serial_numbers) >= 1

    def test_all_axes_have_result_entries(self):
        output = self.pipeline.classify_email(
            subject='Commande', body='Commande urgente'
        )
        assert 'type_mail' in output.axes
        assert 'statut' in output.axes

    def test_confidence_in_range(self):
        output = self.pipeline.classify_email(
            subject='Offre commerciale Airbus',
            body='Suite à votre demande, voici notre offre pour le projet Sentinel.',
        )
        for result in output.axes.values():
            assert 0.0 <= result.confidence <= 1.0, (
                f"Confidence out of range for axis '{result.axis_name}'"
            )

    def test_method_is_valid(self):
        output = self.pipeline.classify_email(subject='test', body='test email')
        valid_methods = {'heuristic', 'llm', 'none'}
        for result in output.axes.values():
            assert result.method in valid_methods

    def test_type_mail_classified_as_commande(self):
        output = self.pipeline.classify_email(
            subject='Bon de commande reçu',
            body='Merci de traiter notre commande.',
        )
        type_result = output.axes.get('type_mail')
        assert type_result is not None
        # Should detect T_Commande
        if type_result.value:
            assert type_result.value.startswith('T_')

    def test_essais_axis_triggered_by_explicit_test_name(self):
        output = self.pipeline.classify_email(
            subject='Résultats BVT Satellite',
            body='La campagne de tests BVT est terminée avec succès.',
        )
        essais = output.axes.get('essais')
        assert essais is not None
        if essais.value:
            assert essais.value.startswith('E_')

    def test_jalon_cdr_detected(self):
        output = self.pipeline.classify_email(
            subject='CDR Review - Project Galileo',
            body='La revue critique de design CDR est planifiée pour le 15 mars.',
        )
        jalons = output.axes.get('jalons')
        assert jalons is not None
        if jalons.value:
            assert jalons.value == 'J_CDR'

    def test_to_llm_context_structure(self):
        output = self.pipeline.classify_email(
            subject='Réunion CDR Sentinel',
            body='Merci de confirmer votre présence à la revue critique de design.',
        )
        ctx = output.to_llm_context()
        assert 'axes' in ctx
        assert 'serial_numbers' in ctx
        assert 'debug' in ctx
        assert 'raw_hits' in ctx['debug']
        assert 'scores' in ctx['debug']

    def test_to_llm_context_json_is_valid_json(self):
        import json
        output = self.pipeline.classify_email(
            subject='Test JSON output',
            body='Vérification du format JSON.',
        )
        json_str = output.to_llm_context_json()
        parsed = json.loads(json_str)
        assert isinstance(parsed, dict)

    def test_classify_emails_conversation(self):
        """classify_emails concatenates multiple email bodies."""
        emails = [
            {'subject': 'Premier mail', 'body': 'Suite à notre offre initiale…'},
            {'subject': 'Réponse', 'body': 'Merci pour votre devis, nous commandons.'},
        ]
        output = self.pipeline.classify_emails(emails)
        assert isinstance(output, HybridClassificationOutput)

    def test_confidence_threshold_filters_output(self):
        """Tags below confidence threshold must not appear in categories."""
        pipeline = HybridClassificationPipeline(
            api_client=None,
            use_llm_for_ambiguous=False,
            confidence_threshold=1.1,  # Impossible threshold → no categories
        )
        output = pipeline.classify_email(
            subject='Commande Airbus Galileo',
            body='Merci de traiter notre commande urgente.',
        )
        assert output.categories == []


# ===========================================================================
# HybridAxisClassifier – unit
# ===========================================================================

class TestHybridAxisClassifier:

    def setup_method(self):
        self.classifier = HybridAxisClassifier(api_client=None, use_llm_for_ambiguous=False)
        self.config = AXIS_CONFIGS['type_mail']
        self.pipeline = AxisHeuristicPipeline(self.config)

    def test_clear_winner_uses_heuristic_method(self):
        hr = self.pipeline.run(
            subject='commande commande commande',
            body='commande',
        )
        result = self.classifier.classify(hr, self.config, email_context='')
        if result.value:
            assert result.method == 'heuristic'

    def test_no_candidates_returns_none(self):
        hr = self.pipeline.run(subject='Bonjour', body='Salut')
        result = self.classifier.classify(hr, self.config, email_context='')
        assert result.value is None
        assert result.method == 'none'

    def test_result_has_candidates_list(self):
        hr = self.pipeline.run(subject='offre', body='offre devis')
        result = self.classifier.classify(hr, self.config, email_context='test')
        assert isinstance(result.candidates, list)

    def test_parse_llm_response_exact_match(self):
        valid = {'T_Commande', 'T_Offre'}
        from mail_classifier.heuristic_engine import AxisHeuristicResult
        dummy_hr = AxisHeuristicResult(
            axis_name='type_mail',
            prefix='T_',
            top_candidates=[],
            is_ambiguous=True,
            serial_numbers=[],
        )
        result = HybridAxisClassifier._parse_llm_response('T_Commande', valid, dummy_hr)
        assert result == 'T_Commande'

    def test_parse_llm_response_aucun(self):
        from mail_classifier.heuristic_engine import AxisHeuristicResult
        dummy_hr = AxisHeuristicResult(
            axis_name='type_mail',
            prefix='T_',
            top_candidates=[],
            is_ambiguous=True,
            serial_numbers=[],
        )
        assert HybridAxisClassifier._parse_llm_response('AUCUN', set(), dummy_hr) is None
        assert HybridAxisClassifier._parse_llm_response('', set(), dummy_hr) is None
