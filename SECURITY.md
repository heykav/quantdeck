# Security policy

## Scope

quantdeck is a backtesting library and CLI. It has no live trading engine,
does not connect to broker accounts and does not handle credentials. The
most relevant issues are things like unsafe handling of strategy files,
CSV input or the local SQLite results file, and problems in the GitHub
Actions workflows.

## Supported versions

Only the latest commit on `main` is supported. There are no maintained
release branches.

## Reporting a vulnerability

Please do not open a public issue for a security problem.

- Preferred: use GitHub private vulnerability reporting on this repository
  (Security tab, "Report a vulnerability").
- Alternatively, email heykavofficial@gmail.com.

Include what you found, how to reproduce it, and the affected commit if you
know it.

This is a personal project maintained on a best-effort basis. There is no
guaranteed response time, but reports will be read and acknowledged when
possible, and fixes will be credited to the reporter unless they prefer
otherwise.
