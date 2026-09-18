# Translation runtime fix

The local translation failure in the previous final build was caused by an overly narrow import path for `IndicProcessor` on current IndicTransToolkit installations.

The adapter now uses the official current import first:

```python
from IndicTransToolkit.processor import IndicProcessor
```

and retains a fallback import for older environments.

A direct diagnostic script is also included:

```powershell
python scripts/test_translation.py --src hin_Deva --tgt sat_Olck --text "पौधों को जीवित रहने और बढ़ने के लिए पानी की आवश्यकता होती है।"
```

The API will also log the full model exception in the FastAPI terminal instead of hiding it.
