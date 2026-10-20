# Container boundary

Generated code runs as an unprivileged user with a read-only root, no Linux capabilities, no-new-privileges, memory/CPU/PID limits and bounded temporary storage. Only its own candidate is mounted read-only. Host home, credentials, environment, Docker socket and other roles' files are never mounted. Network is disabled unless a trusted verifier connects the candidate to a dedicated internal test network. The model cannot select a command, host mount, image or network.

These are project-authored notes based on Docker's container run documentation, retrieved 2026-10-20. They describe the required boundary, not evidence that a particular execution passed.
