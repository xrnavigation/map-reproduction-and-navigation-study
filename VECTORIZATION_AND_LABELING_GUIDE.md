# Vectorization and Labeling Guide

## 1. Goal
Create participant GeoJSON maps that can be scored against baseline maps with reproducible labels and consistent geometry quality.

---

## 2. Folder and File Rules
- Participant source maps are stored in:
  - `blind_participants/p*/`
  - `sighted_participants/p*/`
- Participant photos are reference-only and stored in `images/` subfolders.
- Vectorized GeoJSON must remain in each participant folder and follow:
  - `Blind_p<id>_Spatial_Knowledge_map_<n>.geojson`
  - `Sighted_p<id>_Spatial_Knowledge_map_<n>.geojson`

---

## 3. Source of Truth
The baseline map is the single source of truth for:
- object existence
- naming
- geometry type
- relative positioning

Participant drawings are interpreted relative to the baseline, not vice versa.

---

## 4. Labeling Standard

### 4.1 Canonical Naming
- Use baseline object names exactly (case-insensitive allowed, spelling must match).
- Do not introduce synonyms unless present in baseline.
- If no matching baseline object exists:
  - assign a descriptive name
  - mark as a potential extra feature

### 4.2 Geometry Type Rules
Preserve parity with baseline:
- Rooms → `Polygon`
- Paths / roads / walkways → `LineString`
- Landmarks → `Point`

### 4.3 Required Properties
Each feature must include:
- `name`
- `type` (if required by editor)
- valid `geometry`

---

## 5. Vectorization Procedure (per participant, per map)

1. Open participant photo and corresponding baseline map (`map_n`).
2. Recreate each drawn object using the baseline coordinate system.
3. Assign the closest canonical `name` from baseline.
4. Handle imperfect drawings:
   - prioritize semantic intent over exact shape
   - snap geometry to nearest baseline structure
   - avoid overfitting to noise or drawing artifacts
5. Validate geometry:
   - polygons are closed and non-self-intersecting
   - lines represent intended paths
   - points represent intended landmarks
6. Save GeoJSON in participant folder (not inside `images/`).

---

## 6. Preset Objects Excluded from Scoring

These objects must not be included in scoring calculations.

### Map 2 exclusions
- Breakroom
- Flagpole
- Elevator
- Top 2 walkways (highest Y-centroid walkways)

### Map 3 exclusions
- Dance Studio
- Water Machine
- Top walkway (highest Y-centroid walkway)
- Bottom walkway (lowest Y-centroid walkway)

---

## 7. Two-Annotator Reconciliation Workflow

1. Annotator A and Annotator B independently create GeoJSON files.
2. Compare features using:
   - `name`
   - geometry type
   - centroid proximity
   - polygon area / line length

### 7.1 Matching Thresholds
- Points: centroid distance ≤ 5 units
- Lines: midpoint distance ≤ 10 units
- Polygons: centroid distance ≤ 10 units

3. Record discrepancies in a shared table with:
- `participant_id`
- `map_id`
- `object_name_baseline`
- `annotator_a_label`
- `annotator_b_label`
- `issue_type`
- `resolution_decision`
- `resolved_by`
- `resolution_date`

### 7.2 Discrepancy Categories
- Label mismatch
- Geometry type mismatch
- Shape mismatch
- Position mismatch
- Missing / Extra feature

4. Resolve discrepancies in joint review using baseline as authority.

### 7.3 Conflict Resolution Priority
1. Baseline naming
2. Geometry type correctness
3. Spatial position
4. Shape detail

5. If unresolved:
   - escalate to third reviewer
   - record final decision

6. Publish one final GeoJSON in participant folder.
7. Store alternate versions in `archive/` if needed.

---

## 8. QA Checklist Before Scoring
- File name contains correct map number.
- Feature names are canonical and consistent.
- No duplicate features.
- Geometry types match object semantics.
- GeoJSON parses without errors.
- Preset objects are excluded from scoring.

---

## 9. Output Artifacts from Scoring Script
Running `audiom_map_similarity_analysis.py` creates:
- `map_similarity_results.xlsx` (row 2 contains formula descriptions)

Participant GeoJSON files remain the canonical vectorized outputs.

---

## 10. Recommended Peer Review Cadence
- Weekly calibration: both annotators vectorize the same 2 maps.
- Measure agreement at object level (`label + geometry type`).
- If agreement < 95%:
  - perform additional calibration before continuing.
