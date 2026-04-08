# map-reproduction-and-navigation-study

These are the map files for the map reproduction and navigation study.

## Quick Run

Run everything (create venv, install dependencies, run analysis):

```bash
./run_analysis.sh
```

Output file:

- `map_similarity_results.xlsx` (two sheets: `blind`, `sighted`)

## Manual Run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python audiom_map_similarity_analysis.py
```
