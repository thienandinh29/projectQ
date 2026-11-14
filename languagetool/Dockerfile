# LanguageTool 6.8 HTTP server, English only, no n-gram data (specs/writing/step-2.2.md).
# Built from LanguageTool's own artifacts on Maven Central; every jar is checked against jars.sha256.
FROM maven:3.9.9-eclipse-temurin-17 AS build
WORKDIR /build
COPY pom.xml jars.sha256 ./
RUN mvn -B -q --strict-checksums dependency:copy-dependencies -DoutputDirectory=libs \
 && cd libs && sha256sum -c --strict --quiet ../jars.sha256 \
 && [ "$(ls *.jar | wc -l)" = "$(wc -l < ../jars.sha256)" ]

FROM eclipse-temurin:17-jre
RUN useradd --uid 10002 --no-create-home --shell /usr/sbin/nologin lt
COPY --from=build /build/libs /opt/languagetool/libs
USER lt
EXPOSE 8010
# 1 GB heap: measured at about 640 MB resident on a 300-word essay (step 2.2).
ENV JAVA_OPTS="-Xmx1g"
HEALTHCHECK --interval=10s --timeout=5s --start-period=60s --retries=6 \
    CMD bash -c 'exec 3<>/dev/tcp/127.0.0.1/8010'
CMD ["sh", "-c", "exec java $JAVA_OPTS -cp '/opt/languagetool/libs/*' org.languagetool.server.HTTPServer --port 8010 --public"]
