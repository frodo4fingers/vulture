# Evidence and safety basis

Last reviewed: 3 August 2026.

## Scope of the claims

Vulture is a behavioral reminder, not a clinical assessment tool. Its posture
scores are normalized webcam-landmark differences from the user's own
calibration. They must not be described as spinal curvature, diagnosis,
treatment need, injury risk, hydration status, eye health, fatigue, fitness, or
work performance.

The movement catalog follows conservative instructions and doses from
traceable public-health or occupational-health guidance. This makes the
prompts auditable; it does **not** prove that a particular desk exercise
prevents injury or treats pain.

## What the evidence supports

### Interrupting sedentary work

- WHO recommends limiting sedentary time and replacing it with physical
  activity of any intensity. It does not prescribe one exact break cadence.
- HSE recommends short, frequent display-screen breaks or changes of activity
  and says timing depends on the work. Its example is 5-10 minutes each hour.
  OSHA similarly suggests a five-minute break from computer tasks each hour.
- Systematic reviews report favorable acute glucose and insulin responses when
  prolonged sitting is interrupted with physical activity. Reviews comparing
  standing and light walking generally find larger acute effects from walking.
  These studies do not establish long-term disease prevention.
- A 2024 frequency meta-analysis found a modest glucose advantage for
  interruptions at least every 30 minutes over less frequent protocols, but
  rated the evidence low certainty and found no significant advantage for
  several other outcomes.

### Micro-breaks and work

Albulescu et al. defined micro-breaks as pauses under ten minutes. Their
meta-analysis found improved vigor and reduced fatigue on average. Performance
effects varied with task and duration, and short breaks did not consistently
improve demanding cognitive work. Vulture therefore offers quiet, social,
off-screen, and lightly active resets without claiming one superior recovery
technique or a productivity gain.

### Eye comfort

The American Optometric Association recommends distance viewing, regular
blinking, appropriate viewing distance, and rest breaks for digital eye strain.
The exact 20-minute/20-second schedule is not established as treatment.
Wilkins et al., a small controlled study of 30 young participants performing a
40-minute tablet task, found no significant symptom or performance effect from
20-second breaks every 5, 10, or 20 minutes.

Vulture therefore labels these as comfort cues and excludes palming, eye yoga,
forced eye rotations, blue-light products, and disease-prevention claims.

### Water, tea, and coffee

Fluid needs vary with body size, diet, activity, environment, health
conditions, pregnancy, and medication. The water channel is a convenience cue,
not a daily target or instruction to drink despite thirst or medical advice.
Tea and coffee are offered as reasons to step away; caffeine is optional.

### Guided movements

CCOHS and NHS guidance supplies the techniques and conservative doses used in
the catalog. Workplace-exercise reviews report possible reductions in
musculoskeletal pain, but heterogeneity and risk of bias prevent firm
treatment or prevention claims.

A 2026 review of 19 randomized trials reported improvements in neck/shoulder
pain and neck disability from workplace micro-exercise programs. Certainty
ranged from moderate to very low, heterogeneity was high, and isolated reminder
doses were not tested.

A randomized crossover trial in 23 adults with medication-controlled type 2
diabetes tested half-squats, calf raises, gluteal contractions, and knee raises.
Six minutes each hour reduced acute post-meal glucose and insulin compared with
uninterrupted sitting; three minutes each half-hour did not in that trial.
Vulture's shorter simple-resistance sampler varies activity and does not claim
to reproduce the metabolic protocol.

### Breathing and restorative views

A remote randomized trial compared daily five-minute breathwork practices with
mindfulness meditation over one month. Exhale-focused cyclic sighing produced
larger mood improvements and reduced respiratory rate. Vulture offers an easy,
slightly longer exhale without fast-only breathing, forced depth, or breath
holding, and does not claim that one pause treats stress or anxiety.

A laboratory study of 150 students found fewer sustained-attention lapses
after a 40-second green-roof view than after a concrete-roof view. This is a
promising single study, so greenery remains an optional version of the
distance-view cue rather than a universal prescription.

## Product choices, not clinical recommendations

The default plan uses:

- 20 seconds of shuffled distance, greenery, blink, or closed-eye comfort every
  20 minutes;
- 2 minutes of shuffled position change, standing, walking, or guided movement
  every 30 minutes;
- a neutral 30-second water cue every 60 minutes;
- a 5-minute shuffled tea/coffee, walk, breathing, off-screen, or guided reset
  every 90 minutes.

No source validates that complete set as a universal prescription. Existing
0.2.0 settings retain the previous distance-eye and combined
walk/water/tea/coffee activity mix; water, greenery, and longer-reset additions
remain disabled until the user enables them. New profiles start with the full
balanced plan.

Activity and exercise choices use persisted shuffle bags. Every eligible item
appears once before a bag refills, and cycle boundaries avoid an immediate
repeat when more than one item is eligible. Water is the intentional
single-item recurring exception. This is a product behavior, not a scientific
claim.

## Included movements

| Movement | Dose | Primary source |
| --- | --- | --- |
| Easy desk-side walk | 5 minutes | OSHA computer-task break |
| Seated chest stretch | Hold 5-10 seconds; repeat 5 times | NHS sitting exercises |
| Shoulder shrug and release | Hold 3-5 seconds; repeat 2-3 times | CCOHS workstation stretching |
| Gentle wrist side-bend | Hold each side 3-5 seconds; 3 cycles per wrist | CCOHS workstation stretching |
| Seated hip marching | 5 lifts per leg | NHS sitting exercises |
| Seated ankle point and flex | 2 sets of 5 per foot | NHS sitting exercises |
| Sit-to-stand | 5 slow repetitions | NHS strength exercises |
| Supported calf raise | 5 slow repetitions | NHS strength exercises |
| Head glide | Hold briefly; repeat up to 5 times | CCOHS workstation stretching |
| Shoulder-blade squeeze | Hold up to 5 seconds; repeat up to 5 times | CCOHS workstation stretching |
| Slow shoulder rolls | 5 backward, then 5 forward | CCOHS workstation stretching |
| Finger opening sequence | 3 slow rounds per hand | CCOHS workstation stretching |
| Simple resistance circuit | One slow 2-3 minute round | Homer et al. trial components |

## Movement safety

Use a stable, non-wheeled chair and a clear floor area. Move slowly, breathe
normally, and stay within a comfortable range. Do not bounce, force a joint, or
continue through pain.

Stop for pain, severe discomfort, dizziness, chest discomfort, unusual
breathlessness, numbness, or loss of balance. New one-sided calf pain or
swelling is not ordinary stiffness and may need urgent assessment.

People with an injury, recent surgery, osteoporosis, significant balance
impairment, or another condition affecting exercise should ask a qualified
clinician which movements are suitable.

## Source ledger

1. World Health Organization, *WHO Guidelines on Physical Activity and
   Sedentary Behaviour* (2020):
   <https://www.who.int/publications/i/item/9789240015128>
2. US Occupational Safety and Health Administration, *Computer Workstations:
   Work Process and Recognition*:
   <https://www.osha.gov/etools/computer-workstations/work-process>
3. Canadian Centre for Occupational Health and Safety, *Office Ergonomics:
   Stretching at the Workstation*:
   <https://www.ccohs.ca/oshanswers/ergonomics/office/stretching.html>
4. UK National Health Service, *Sitting exercises*:
   <https://www.nhs.uk/live-well/exercise/sitting-exercises/>
5. UK National Health Service, *Strength exercises*:
   <https://www.nhs.uk/live-well/exercise/strength-exercises/>
6. Loh et al., activity-break systematic review and meta-analysis,
   *Sports Medicine* (2020):
   <https://pmc.ncbi.nlm.nih.gov/articles/PMC6985064/>
7. Peddie et al., sitting, standing, and activity-break crossover trial,
   *PLOS ONE* (2021):
   <https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0244841>
8. Buffey et al., standing and light-walking systematic review and
   meta-analysis, *Sports Medicine* (2022):
   <https://doi.org/10.1007/s40279-022-01649-4>
9. Albulescu et al., micro-break systematic review and meta-analysis,
   *PLOS ONE* (2022):
   <https://doi.org/10.1371/journal.pone.0272460>
10. UK Health and Safety Executive, *Work routine and breaks*:
    <https://www.hse.gov.uk/msd/dse/work-routine.htm>
11. American Optometric Association, *Computer vision syndrome*:
    <https://www.aoa.org/healthy-eyes/eye-and-vision-conditions/computer-vision-syndrome>
12. Wilkins et al., *20-20-20 Rule: Are These Numbers Justified?* (2023):
    <https://pubmed.ncbi.nlm.nih.gov/36473088/>
13. Tersa-Miralles et al., workplace-exercise systematic review,
    *BMJ Open* (2022):
    <https://bmjopen.bmj.com/content/12/1/e054288>
14. Homer et al., simple resistance activity crossover trial,
    *Diabetes Care* (2021):
    <https://pubmed.ncbi.nlm.nih.gov/33905343/>
15. Yin et al., sedentary-interruption frequency systematic review and
    meta-analysis (2024):
    <https://pubmed.ncbi.nlm.nih.gov/39630056/>
16. Yaghoubitajani et al., workplace micro-exercise systematic review and
    meta-analysis, *Scientific Reports* (2026):
    <https://pubmed.ncbi.nlm.nih.gov/42297926/>
17. Balban et al., structured respiration randomized trial,
    *Cell Reports Medicine* (2023):
    <https://pubmed.ncbi.nlm.nih.gov/36630953/>
18. Lee et al., green-view micro-break laboratory study,
    *Journal of Environmental Psychology* (2015):
    <https://doi.org/10.1016/j.jenvp.2015.04.003>

The localized machine-readable catalogs under
`src/vulture/resources/exercises/` record which sources support each movement.
