# Review finding merge correction

The live controlled TLS fixture produced a static observation at the `verify=False`
keyword and an AI observation covering the surrounding call. Both used the same
issue title but different starting lines. The previous merge compared only the
file and starting line, so it kept both. That comparison also incorrectly removed
different issues reported at the same starting line.

The merge now compares the normalized issue title, file, pinned commit SHA and
overlapping line spans. Matching observations keep the first result; deterministic
static findings and their validated patch are processed first. Different titles,
disjoint locations, files and commits remain separate. This is conservative
duplicate detection, not semantic equivalence or proof of exploitability.

Eight regression cases cover the wider AI call span, case/punctuation variants,
repeated AI results, distinct issues at the same line, separate calls and separate
files/commits. The full Python suite passes 59 tests. Dependencies and frontend
source are unchanged by this correction.

Historical review records and human decisions are not rewritten. A completed
review for a given PR head is intentionally reused. After deployment, create a
new commit on the isolated test PR branch (for example, clarify its module
docstring), then start a new review for the same PR number. It must show the new
head SHA. Earlier reviews keep their original findings.

The downloaded controlled-fixture patch was checked against PR #2 at commit
`3c0131edb5ee793d3da7f5e8f3867454ca0be665`: `git apply --check` passed against a
temporary copy; the only change was `verify=False` to `verify=True`, and Python
syntax remained valid. The fixture function was not executed. This verifies patch
transport/applicability for one example, not a deployed fix or general model quality.
