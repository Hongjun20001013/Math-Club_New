# Skill-loop pilot deploy checklist

Do not deploy until this list is complete and the owner has approved production salt configuration.

1. Confirm automated tests: `python3 -m unittest tests.test_skill_loop_gate -v`
2. Confirm local browser E2E passed (desktop + mobile widths).
3. Feature flag `SKILL_LOOP_PILOT` remains off until the go-live window.
3b. Pack-backed `SKILL_REPAIR` remains off (default). If unset, `SKILL_LOOP_PILOT` can also enable Repair; `SKILL_REPAIR=false` wins.
4. Set `SKILL_LOOP_ASSIGN_SALT` in the host secret store before enabling the flag.
   - Generate a high-entropy secret. Do not reuse the local dev salt.
   - Do not put the salt in git, logs, HTML, reports, or client JavaScript.
   - Missing salt in production disables the pilot and refuses assignment.
5. Changing salt later must not rehash existing `skill_loop_assignments` rows.
6. Schema-only migrate (CREATE IF NOT EXISTS only) requires a separate written approval.
   `python3 scripts/skill_loop_migrate.py --schema-only --db <local-copy.db>`
   Production path additionally requires `--allow-render-production` and is schema-only.
   Failed schema-only runs roll back in one transaction. Successful empty tables stay;
   do not DROP them unless the owner gives written rollback approval.
7. Ordinary `--apply` (schema + seed) still refuses `/var/data`. Never run it on production.
   Code rollback / Render rollback does not delete database tables.
8. Do not modify `data/question_bank.json`.
9. Teacher-publish remaining draft items before students are invited.
10. Reports must keep the bilingual “pilot only / not instructional effectiveness” disclaimer.

Production salt configuration is not performed in this slice. Wait for explicit deploy approval.
