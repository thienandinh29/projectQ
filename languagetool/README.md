# LanguageTool service

The grammar and spelling checker for essays (`specs/writing/step-2.2.md`). It runs as our own container, so essays never
leave the machine. LanguageTool is LGPL-2.1; we use it unmodified, as a separate service.

- Start: `docker compose --profile writing up -d languagetool`, and set `LANGUAGETOOL_URL=http://languagetool:8010` in
  `.env` so the worker uses it. Without it, essays are measured without a grammar check (the page says so).
- Memory: `-Xmx1g`; about 640 MB resident on a 300-word essay (measured 14 Nov 2026 outside Docker).
- Upgrade: change the version in `pom.xml`, then regenerate the pins and commit both:

```bash
mvn -B -q dependency:copy-dependencies -DoutputDirectory=libs && (cd libs && sha256sum *.jar | sort -k2) > jars.sha256
```
