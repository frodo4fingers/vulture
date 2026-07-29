# Evidence and safety basis

## Scope of the claims

Vulture is a behavioral reminder, not a clinical assessment tool. Its posture
scores are normalized webcam-landmark differences from the user's own
calibration. They must not be described as spinal curvature, craniovertebral
angle, scapular position, diagnosis, treatment need, or injury risk.

The movement catalog follows conservative instructions and doses published by
authoritative public-health or occupational-health organizations. This means
the prompts are traceable; it does **not** prove that a particular desk
exercise prevents injury or treats pain.

## What the evidence supports

- The World Health Organization recommends limiting sedentary time and
  replacing it with physical activity of any intensity, including light
  activity. It does not prescribe one exact break interval.
- OSHA recommends a five-minute break from computer tasks every hour, which may
  include looking away, stretching, standing, or walking.
- CCOHS recommends regular workstation breaks and publishes the shoulder-shrug
  and gentle wrist-movement instructions used in the catalog.
- NHS sitting and strength guidance publishes the exact instructions and doses
  used for the chest stretch, hip march, ankle movement, sit-to-stand, and
  supported calf raise.
- A systematic review found that interrupting prolonged sitting with activity
  improves acute glucose and insulin outcomes, while optimal timing and
  long-term implications remain uncertain.
- A small crossover trial found acute benefits from two-minute walking breaks
  every 30 minutes for selected insulin and leg-blood-flow outcomes. Its
  protocol should not be generalized into a universal prescription.
- A workplace-exercise systematic review reported possible pain benefit, but
  heterogeneity and risk of bias prevent firm prevention or treatment claims.

## Product choices, not clinical recommendations

The following defaults are engineering and user-experience decisions:

- how many seconds a deviation must persist;
- calibration separation thresholds;
- notification cooldown;
- five reminders in a 20-minute window before an exercise offer;
- random non-repeating exercise selection;
- a 55-minute independent break timer.

These settings are deliberately presented as configurable. No cited source
validates a camera score threshold or the five-in-20 escalation rule.

## Included movements

| Movement | Dose | Primary source |
| --- | --- | --- |
| Easy desk-side walk | 5 minutes | OSHA hourly computer-task break |
| Seated chest stretch | Hold 5–10 seconds, repeat 5 times | NHS sitting exercises |
| Shoulder shrug and release | Hold 3–5 seconds, repeat 2–3 times | CCOHS workstation stretching |
| Gentle wrist side-bend | Hold each side 3–5 seconds, 3 cycles per wrist | CCOHS workstation stretching |
| Seated hip marching | 5 lifts per leg | NHS sitting exercises |
| Seated ankle point and flex | 2 sets of 5 per foot | NHS sitting exercises |
| Sit-to-stand | 5 slow repetitions | NHS strength exercises |
| Supported calf raise | 5 slow repetitions | NHS strength exercises |

## Excluded by default

The catalog intentionally excludes ballistic or forceful end-range stretching,
loaded deep spinal flexion/twisting, jumping, unsupported single-leg balance,
deep squats, floor exercises, and diagnosis-specific rehabilitation. These can
be unsuitable for some users and cannot be screened safely by a webcam app.

Users should stop for pain, severe discomfort, dizziness, chest discomfort,
unusual breathlessness, numbness, or loss of balance. New one-sided calf pain
or swelling is not ordinary stiffness and may need urgent assessment.

## Source ledger

1. World Health Organization, *WHO Guidelines on Physical Activity and
   Sedentary Behaviour*, 25 November 2020:
   <https://www.who.int/publications/i/item/9789240015128>
2. US Occupational Safety and Health Administration, *Computer Workstations:
   Work Process and Recognition*:
   <https://www.osha.gov/etools/computer-workstations/work-process>
3. Canadian Centre for Occupational Health and Safety, *Office Ergonomics:
   Stretching at the Workstation*, confirmed current 4 February 2025:
   <https://www.ccohs.ca/oshanswers/ergonomics/office/stretching.html>
4. UK National Health Service, *Sitting exercises*, reviewed 18 January 2024:
   <https://www.nhs.uk/live-well/exercise/sitting-exercises/>
5. UK National Health Service, *Strength exercises*, reviewed 28 February 2024:
   <https://www.nhs.uk/live-well/exercise/strength-exercises/>
6. Loh et al., *Effects of Interrupting Prolonged Sitting with Physical
   Activity Breaks on Blood Glucose, Insulin and Triacylglycerol Measures: A
   Systematic Review and Meta-analysis*, *Sports Medicine* (2020):
   <https://pmc.ncbi.nlm.nih.gov/articles/PMC6985064/>
7. Peddie et al., *The effects of prolonged sitting, prolonged standing, and
   activity breaks: a randomised crossover trial*, *PLOS ONE* (2021):
   <https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0244841>
8. Tersa-Miralles et al., *Effectiveness of workplace exercise interventions
   in the treatment of musculoskeletal disorders in office workers: a
   systematic review*, *BMJ Open* (2022):
   <https://bmjopen.bmj.com/content/12/1/e054288>

The machine-readable catalog at
`src/vulture/resources/exercises/catalog.json` records which source supports
each movement.
