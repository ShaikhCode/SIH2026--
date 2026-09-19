LANGUAGES = {
    'eng_Latn': {'name':'English','script':'latin'},
    'hin_Deva': {'name':'हिन्दी','script':'devanagari'},
    'sat_Olck': {'name':'ᱥᱟᱱᱛᱟᱲᱤ','script':'olchiki'},
}

def validate_language(code: str) -> None:
    if code not in LANGUAGES:
        raise ValueError(f'Unsupported language code: {code}')
