# Local GPS reports

Place a private GPS report in this directory for local inspection, or set
`PLAYERIQ_LOCAL_REPORT` to its path when running the optional real-report test.
The report is not included in Git. `.gitignore` ignores every other file here.

Never use real athlete names or report pages in committed test fixtures. The
automated suite generates a synthetic PDF in a temporary directory instead.
