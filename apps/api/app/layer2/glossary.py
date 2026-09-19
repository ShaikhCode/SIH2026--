from .models import Concept

# Santhali terms intentionally remain empty until verified language data is reviewed by a qualified/native reviewer.
GLOSSARY = {
    'water': {'eng_Latn':'water','hin_Deva':'पानी','sat_Olck':''},
    'plants': {'eng_Latn':'plants','hin_Deva':'पौधे','sat_Olck':''},
    'growth': {'eng_Latn':'growth','hin_Deva':'विकास','sat_Olck':''},
    'need': {'eng_Latn':'need','hin_Deva':'आवश्यकता','sat_Olck':''},
    'sunlight': {'eng_Latn':'sunlight','hin_Deva':'सूरज की रोशनी','sat_Olck':''},
}

def preferred_term(concept_id: str, language: str) -> str:
    return GLOSSARY.get(concept_id, {}).get(language, '')

def glossary_matches(concepts: list[Concept], target_text: str, target_language: str) -> list[str]:
    lower = target_text.lower()
    missing = []
    for c in concepts:
        term = preferred_term(c.concept_id, target_language)
        if term and term.lower() not in lower:
            missing.append(c.concept_id)
    return missing
