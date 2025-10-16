# NameGenderMapper

A **memory-efficient Python tool** to detect gender from names in large CSV datasets.  
It can process **first names alone** or **full names** (first and last combined in a single column).  
The script generates **gender predictions**, **confidence scores**, and flags ambiguous names for manual review. 

---

## Features

- Processes **large CSV files** efficiently using streaming (line by line).
- Adds three new columns to your CSV:
    - `Gender` — predicted gender (`M`, `F`, `Unknown`)
    - `GenderConfidence` — confidence score between 0 and 1
    - `GenderSource` — source of prediction (`mapped`, `country-mapped`, `gender-guesser`, `unknown`)
- **Country-specific mapping**: If your reference CSV has a `country` column, the script will try to use country-specific gender data first.
- **Fallback** using [`gender-guesser`](https://pypi.org/project/gender-guesser/) if no high-confidence mapping is available.
- Generates an **audit CSV** for ambiguous or low-confidence first names for manual review.

---

## Requirements

- Python 3.7+
- Optional (for better fallback): `gender-guesser`

```bash
pip install gender-guesser

```

## Usage

Place your files in the project folder:

```text
NameGenderMapper.py         — the main script
reference-names.csv         — CSV with at least name and gender columns (optional country)
file-to-sort.csv                   — the dataset you want to process
```


Run the script:

```bash
python NameGenderMapper.py
````

Output files:

```text
people_with_gender.csv      — main output with gender info added
ambiguous_first_names.csv   — audit file for manual review
```

Inside the script, you can adjust:

```text
GENDER_FILE                 — path to your reference CSV
INPUT_FILE                  — path to your dataset CSV
OUTPUT_FILE                 — output CSV filename
AUDIT_FILE                  — audit CSV filename
CONF_THRESHOLD              — minimum confidence to accept a mapping (0..1)
MIN_COUNT_FOR_CONFIDENCE    — names with fewer occurrences are treated as lower-confidence
```

## Notes

The script auto-detects CSV delimiters (comma, tab, semicolon, or pipe).

Works with full-name columns; the script will attempt to extract the first name automatically for gender prediction.

---

## License

This project is licensed under the MIT License.
