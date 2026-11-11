# Deliverable status

This clean source package is intended for a new GitHub repository. No remote repository has been created or pushed by this preparation step.

| Item | Status | Required action |
|---|---|---|
| Source and README | Prepared; clean-copy checks recorded in VALIDATION.md | Publish the extracted project using the final delivery's GitHub guide; confirm access |
| Report | 18-page English PDF and editable LaTeX supplied separately | Fill team/course/contribution/acknowledgement fields and confirmed links; recompile |
| Video | Seven-minute script and executable recording handoff supplied separately | Assign presenters, record, edit, confirm 5–8 minutes, upload and check access |
| GitHub URL | **TO BE CONFIRMED** | Add the actual repository URL here, in README and in the report |
| Video URL | **TO BE COMPLETED** | Add a playable link here, in README and in the report |

The course submission is a PDF named `CampusRideMatch-report.pdf`, with working source-repository and video links. The ZIP is a source delivery/archive, not a replacement for the required online repository.

## Recording handoff location

The separate final delivery contains `VIDEO_HANDOFF/`. Copy that directory into the extracted source root (beside `app.py`) when preparing a recording. Then read its `RECORDING_GUIDE.md`; do not run the helper from the outer final-delivery folder, which has no application source beside it.

The main application uses seed credentials `password123`. The video sandbox uses `DemoRide5003!` and its own protected `.runtime/demo.sqlite`. These are distinct fictional datasets. Both runtime directories must remain untracked.

## Report location

The final delivery contains the current PDF and `Report_Source/`. `python Report_Source/build.py` compiles to the parent directory after a TeX distribution with pdflatex is installed. Once finalized, the team may attach the PDF to a GitHub release or add it under `docs/`; only then replace the explicit report-location note with a real link.

No existing development history is supplied or reconstructed. A new initial commit must not be represented as evidence of individual students' earlier work. Contribution statements require team confirmation.
