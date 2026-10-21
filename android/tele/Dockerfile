# Imagen de compilación de la app de la tele: JDK 17, SDK de Android y Gradle para generar el wrapper.
FROM eclipse-temurin:17-jdk-jammy

ARG CMDLINE_TOOLS=11076708
ARG CMDLINE_TOOLS_SHA256=2d2d50857e4eb553af5a6dc3ad507a17adf43d115264b1afc116f95c92e5e258
ARG PLATFORM=android-34
ARG BUILD_TOOLS=34.0.0
ARG GRADLE_VERSION=8.7
ARG GRADLE_SHA256=544c35d6bd849ae8a5ed0bcea39ba677dc40f49df7d1835561582da2009b961d

ENV ANDROID_HOME=/opt/android-sdk \
    ANDROID_SDK_ROOT=/opt/android-sdk \
    GRADLE_USER_HOME=/gradle-cache
ENV PATH=$PATH:/opt/android-sdk/cmdline-tools/latest/bin:/opt/android-sdk/build-tools/${BUILD_TOOLS}:/opt/gradle/bin

RUN apt-get update \
    && apt-get install -y --no-install-recommends unzip curl \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL -o /tmp/tools.zip \
        https://dl.google.com/android/repository/commandlinetools-linux-${CMDLINE_TOOLS}_latest.zip \
    && echo "${CMDLINE_TOOLS_SHA256}  /tmp/tools.zip" | sha256sum -c - \
    && mkdir -p $ANDROID_HOME/cmdline-tools \
    && unzip -q /tmp/tools.zip -d $ANDROID_HOME/cmdline-tools \
    && mv $ANDROID_HOME/cmdline-tools/cmdline-tools $ANDROID_HOME/cmdline-tools/latest \
    && rm /tmp/tools.zip

RUN yes | sdkmanager --licenses > /dev/null \
    && sdkmanager "platforms;${PLATFORM}" "build-tools;${BUILD_TOOLS}" "platform-tools"

# Gradle suelto solo para generar el wrapper; la compilación usa ./gradlew.
RUN curl -fsSL -o /tmp/gradle.zip \
        https://services.gradle.org/distributions/gradle-${GRADLE_VERSION}-bin.zip \
    && echo "${GRADLE_SHA256}  /tmp/gradle.zip" | sha256sum -c - \
    && unzip -q /tmp/gradle.zip -d /opt \
    && mv /opt/gradle-${GRADLE_VERSION} /opt/gradle \
    && rm /tmp/gradle.zip

# El volumen nuevo hereda estos permisos y lo puede escribir el usuario de la máquina.
RUN mkdir -p /gradle-cache && chmod 777 /gradle-cache

WORKDIR /src
