# Deliverable status

The source code is published in the public [CampusRideMatch GitHub repository](https://github.com/hhb232411/CampusRideMatch).

| Item | Status | Required action |
|---|---|---|
| Source and README | Published; clean-copy checks recorded in VALIDATION.md | Keep the submitted report's repository link consistent with this repository |
| Report | 18-page English PDF and editable LaTeX supplied separately | Fill team/course/contribution/acknowledgement fields and confirmed links; recompile |
| Video | Seven-minute script and executable recording handoff supplied separately | Assign presenters, record, edit, confirm 5–8 minutes, upload and check access |
| GitHub URL | [hhb232411/CampusRideMatch](https://github.com/hhb232411/CampusRideMatch) | Add this confirmed URL to the final report |
| Video URL | **TO BE COMPLETED** | Add a playable link here, in README and in the report |

The course submission is a PDF named `CampusRideMatch-report.pdf`, with working source-repository and video links. The ZIP is a source delivery/archive, not a replacement for the required online repository.

## Recording handoff location

The separate final delivery contains `VIDEO_HANDOFF/`. Copy that directory into the extracted source root (beside `app.py`) when preparing a recording. Then read its `RECORDING_GUIDE.md`; do not run the helper from the outer final-delivery folder, which has no application source beside it.

The main application uses seed credentials `password123`. The video sandbox uses `DemoRide5003!` and its own protected `.runtime/demo.sqlite`. These are distinct fictional datasets. Both runtime directories must remain untracked.

## Report location

The final delivery contains the current PDF and `Report_Source/`. `python Report_Source/build.py` compiles to the parent directory after a TeX distribution with pdflatex is installed. Once finalized, the team may attach the PDF to a GitHub release or add it under `docs/`; only then replace the explicit report-location note with a real link.

No existing development history is supplied or reconstructed. A new initial commit must not be represented as evidence of individual students' earlier work. Contribution statements require team confirmation.
